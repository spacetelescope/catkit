from collections import UserDict
import logging
import os
import sys
import threading


# NOTE: "multiprocess" is a 3rd party package and not Python's own "multiprocessing".
# https://github.com/uqfoundation/multiprocess is a fork of multiprocessing that uses "dill" instead of "pickle".
import multiprocess.util as util
from multiprocess import get_context, TimeoutError
from multiprocess.managers import AcquirerProxy, AutoProxy, BarrierProxy, DictProxy, EventProxy, \
    NamespaceProxy, Server, State, SyncManager, ValueProxy, Token, format_exc


DEFAULT_TIMEOUT = 60

# TODO: When using servers across networked machines, the loopback IP won't be viable.
DEFAULT_SHARED_MEMORY_SERVER_ADDRESS = ("127.0.0.1", 6000)  # IP, port.
EXCEPTION_SERVER_ADDRESS = ("127.0.0.1", 6001)  # IP, port.

CONTEXT_METHOD = "spawn"
CONTEXT = get_context(CONTEXT_METHOD)


class CatkitServer(Server):

    # Patch to allow all funcs to be callable without needing to be pre-defined as exposed.
    # This is necessary to dynamically create auto proxies, e.g., particularly those for the devices.
    def serve_client(self, conn):
        '''
        Handle requests from the proxies in a particular process/thread
        '''
        util.debug('starting server thread to service %r',
                   threading.current_thread().name)

        recv = conn.recv
        send = conn.send
        id_to_obj = self.id_to_obj

        while not self.stop_event.is_set():
            try:
                methodname = obj = None
                request = recv()
                ident, methodname, args, kwds = request
                try:
                    obj, exposed, gettypeid = id_to_obj[ident]
                except KeyError as ke:
                    try:
                        obj, exposed, gettypeid = \
                            self.id_to_local_proxy_obj[ident]
                    except KeyError as second_ke:
                        raise ke

                #--------BEGIN PATCH-----------
                # if methodname not in exposed:
                #     raise AttributeError(
                #         'method %r of %r object is not in exposed=%r' %
                #         (methodname, type(obj), exposed)
                #     )
                #----------END PATCH-----------

                #--------BEGIN PATCH-----------
                function = getattr(obj, methodname)  # <-- original
                #function = operator.attrgetter(methodname)(obj)
                #----------END PATCH-----------

                try:
                    #--------BEGIN PATCH-----------
                    # if not hasattr(function, "__self__"):
                    #     # Unbound method so self needs to be explicitly passed.
                    #     args = (obj, *args)
                    #----------END PATCH-----------
                    res = function(*args, **kwds)

                except Exception as e:
                    msg = ('#ERROR', e)
                else:
                    typeid = gettypeid and gettypeid.get(methodname, None)
                    #--------BEGIN PATCH-----------
                    # if isinstance(typeid, dict):
                    #     typeid = typeid.get(args, None)
                    #----------END PATCH-----------

                    if typeid:
                        rident, rexposed = self.create(conn, typeid, res)
                        token = Token(typeid, self.address, rident)
                        msg = ('#PROXY', (rexposed, token))
                    else:
                        msg = ('#RETURN', res)

            except AttributeError:
                if methodname is None:
                    msg = ('#TRACEBACK', format_exc())
                else:
                    try:
                        fallback_func = self.fallback_mapping[methodname]
                        result = fallback_func(
                            self, conn, ident, obj, *args, **kwds
                        )
                        msg = ('#RETURN', result)
                    except Exception:
                        msg = ('#TRACEBACK', format_exc())

            except EOFError:
                util.debug('got EOF -- exiting thread serving %r',
                           threading.current_thread().name)
                sys.exit(0)

            except Exception:
                msg = ('#TRACEBACK', format_exc())

            try:
                try:
                    send(msg)
                except Exception as e:
                    send(('#UNSERIALIZABLE', format_exc()))
            except Exception as e:
                util.info('exception in thread serving %r',
                          threading.current_thread().name)
                util.info(' ... message was %r', msg)
                util.info(' ... exception was %r', e)
                conn.close()
                sys.exit(1)

    # Patch this to correctly handle properties.
    def all_methods(obj):
        '''
        Return a list of names of methods of `obj`
        '''
        temp = []
        for name in dir(obj):
            #--------BEGIN PATCH-----------
            # Properties must be checked on the class and not the instance object such that they aren't called.
            cls = getattr(obj, "__class__", None)
            if cls:
                func = getattr(cls, name, None)
                if func and isinstance(func, property):
                    continue
            #----------END PATCH-----------

            func = getattr(obj, name)
            if callable(func):
                temp.append(name)
        return temp


class Process(CONTEXT.Process):
    def run(self):
        """ Catch exception on child process and save in shared memory manager for parent to read.
            This is executed on the child process.
        """
        try:
            pid = self.pid
            assert pid
            super().run()
        except Exception as error:
            manager = SharedMemoryManager(address=EXCEPTION_SERVER_ADDRESS)
            try:  # Manager may not have been started.
                manager.connect()
            except Exception:
                pass
            else:
                manager.set_exception(pid, error)
                assert manager.get_exception(pid)

            finally:
                raise error

    def join(self, timeout=None):
        """ Join and raise saved exception if one occurred.
            This is executed on the parent process.
        """
        pid = self.pid
        super().join(timeout)
        exitcode = self.exitcode
        if exitcode == 0:
            return
        elif exitcode is None:
            # Process is still running.
            raise TimeoutError(f"The process '{self.name}' on PID {self.pid} failed to join after {timeout} seconds")
        else:
            child_exception = None
            manager = SharedMemoryManager(address=EXCEPTION_SERVER_ADDRESS)
            try:  # Manager may not have been started.
                manager.connect()
            except Exception:
                pass
            else:
                child_exception = manager.get_exception(pid)  # Returns None if pid not in dict.

            if child_exception:
                # Raise the child exception rather than chaining, to facilitate better options for subsequent exception
                # handling.
                raise child_exception
            else:
                raise Exception(f"Child process ('{self.name}' with pid: '{self.pid}') exited with non-zero exitcode: '{self.exitcode}'")


""" There are two main mutex patterns in use here; proxy only mutexes and referent mutexes.
    referent mutexes are those where access to the referent (from the server) are mutexed, e.g., __getattribute__() is
    mutexed. Proxy only mutexes are where the referent is mutexed only by the proxy, i.e., from the client.
    
    Proxy only mutexes are weaker as they require strict API usage such that all referent access is via a proxy, E.g.,
    as is the case for device access via the device enum API. The advantage is that the referent object class requires
    no alterations, e.g., inserting a mutex. However, any indirect access, i.e., from the server will not be mutexed and
    can by-pass any proxy client-side mutex. Again, strict API usage is required.
    
    Referent mutex is where any and all access is mutexed as is mutexed from server-side access. This accounts for
    indirect access, e.g., a device proxy calling a method that obviously gets executed server-side and then access the,
    for example, the shared simulator object. Without a referent mutex a global lock of the sim object, from some
    client, will fail to lock all access as it will only lock (direct) proxy access.
"""


class Mutex:
    """ A container for a shared (reentrant) lock. """

    __slots__ = ("_catkit_mutex", "_catkit_mutex_id", "timeout")#, "from_pid", "_count")

    def __init__(self, *args, lock=None, timeout=None, **kwargs):
        super().__init__(*args, **kwargs)

        # self.from_pid = None
        # self._count = 0

        if lock is None:
            self._catkit_mutex = threading.RLock()
            self._catkit_mutex_id = id(self._catkit_mutex)
            self.timeout = DEFAULT_TIMEOUT if timeout is None else timeout
        elif isinstance(lock, (type(threading.RLock()), type(threading.Lock()))):
            self._catkit_mutex = lock
            self._catkit_mutex_id = id(self._catkit_mutex)
            self.timeout = DEFAULT_TIMEOUT if timeout is None else timeout
        elif isinstance(lock, Mutex):
            self._catkit_mutex = lock.get_mutex()
            self._catkit_mutex_id = lock.get_mutex_id()
            assert id(self._catkit_mutex) == self._catkit_mutex_id
            self.timeout = lock.timeout if timeout is None else timeout
        elif isinstance(lock, Mutex.Proxy):
            self._catkit_mutex = lock
            self._catkit_mutex_id = self._catkit_mutex.get_mutex_id()
            self.timeout = lock.timeout if timeout is None else timeout
        else:
            raise TypeError()

    def __eq__(self, other):
        other = other.get_mutex_id() if isinstance(other, (Mutex, Mutex.Proxy)) else id(other)
        return self.get_mutex_id() == other

    def acquire(self, timeout=None, raise_on_fail=True):
        """
            https://docs.python.org/3/library/multiprocessing.html#multiprocessing.RLock
            The parent semantics for `timeout=None` := timeout=infinity. We have zero use case for this and, instead,
            will use `self.timeout` if `timeout is None`.
        """
        if timeout is None:
            timeout = self.timeout

        locked = self._catkit_mutex.acquire(timeout=timeout)
        if not locked and raise_on_fail:
            raise TimeoutError(f"Failed to acquire lock after {timeout}s (exec on (not from) PID: {os.getpid()}, ID: {self._catkit_mutex_id:#x})")

        # if locked:
        #     self._count += 1
        return locked

    def release(self):
        # self._count -= 1
        return self._catkit_mutex.release()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.release()

    def get_mutex(self):
        return self._catkit_mutex

    def get_mutex_id(self):
        return self._catkit_mutex_id

    #@lru_cache(maxsize=None)
    def clobber(self, new_mutex):
        old_mutex = self._catkit_mutex
        with old_mutex:  # Acquire to ensure nothing else has it before we clobber it.
            self._catkit_mutex = new_mutex

    class Proxy(NamespaceProxy, AcquirerProxy):
        _exposed_ = ("__eq__", "clobber", "get_mutex_id", *NamespaceProxy._exposed_, *AcquirerProxy._exposed_)
        _method_to_typeid_ = {"get_mutex": "MutexProxy"}

        def acquire(self, *args, **kwargs):
            # NOTE: Override since the original signature is constrained.
            return self._callmethod("acquire", args, kwargs)

        def __enter__(self):
            # NOTE: Override so that it calls the above custom acquire.
            return self.acquire()

        def clobber(self, *args, **kwargs):
            return self._callmethod("clobber", args, kwargs)

        def __eq__(self, *args, **kwargs):
            return self._callmethod("__eq__", args, kwargs)

        def get_mutex(self):
            return self._callmethod("get_mutex")

        def get_mutex_id(self):
            return self._callmethod("get_mutex_id")


class Namespace(object):

    # Patch the following to allow for inheritance - functionality of the src isn't required.
    # def __init__(self, **kwds):
    #     self.__dict__.update(kwds)

    def __repr__(self):
        items = list(self.__dict__.items())
        temp = []
        for name, value in items:
            if not name.startswith('_'):
                temp.append('%s=%r' % (name, value))
        temp.sort()
        return '%s(%s)' % (self.__class__.__name__, ', '.join(temp))


class MutexedNamespace(Namespace):  # MutexedObject
    """ Base class for a mutexed object.
        NOTE: Methods are not mutexed server-side so this is not completely thread-safe. They are however, mutexed
        proxy-side so are "thread-safe" within the context of the shared memory manager model.
    """

    __slots__ = ("_catkit_mutex",)  # __dict__ still exists from the base, otherwise we'd have a 1 attr namespace!

    def __new__(cls, *args, lock=None, timeout=None, **kwargs):
        obj = super().__new__(cls)

        # Init mutex.
        if timeout is None and hasattr(cls, "timeout"):
            timeout = cls.timeout
        object.__setattr__(obj, "_catkit_mutex", Mutex(lock=lock, timeout=timeout))
        return obj

    def __init__(self, *args, lock=None, timeout=None, **kwargs):
        # NOTE: lock & timeout are only required for __new__ so we remove them and don't pass them to super.
        super().__init__(*args, **kwargs)

    def copy_from(self, other):
        self.__dict__.update(other.__dict__.copy())

    def __getattribute__(self, item):
        with object.__getattribute__(self, "_catkit_mutex"):
            return object.__getattribute__(self, item)

    def __setattr__(self, name, value):
        with self._catkit_mutex:
            return super().__setattr__(name, value)

    def __delattr__(self, item):
        with self._catkit_mutex:
            return super().__delattr__(item)

    def __enter__(self):
        return object.__getattribute__(self, "_catkit_mutex").__enter__()

    def __exit__(self, *args, **kwargs):
        return object.__getattribute__(self, "_catkit_mutex").__exit__(*args, **kwargs)

    def acquire(self, *args, **kwargs):
        return object.__getattribute__(self, "_catkit_mutex").acquire(*args, **kwargs)

    def release(self, *args, **kwargs):
        return object.__getattribute__(self, "_catkit_mutex").release(*args, **kwargs)

    def get_mutex(self):
        return object.__getattribute__(self, "_catkit_mutex")

    def clobber_mutex(self, *args, **kwargs):
        return object.__getattribute__(self, "_catkit_mutex").clobber(*args, **kwargs)

    class Proxy(Mutex.Proxy, NamespaceProxy):

        _exposed_ = ("getpid", *Mutex.Proxy._exposed_, *NamespaceProxy._exposed_)
        # NOTE: The following are either mutexed server-side (so there's no need to do so from the proxy) or they just
        # shouldn't be mutexed at all, i.e., anything that would block/delay a concurrent acquire attempt (e.g.,
        # "__init__" and "acquire").
        _DONT_PROXY_MUTEX = ("__getattribute__", "__setattr__", "__delattr__", "__enter__", "__exit__", "acquire",
                             "release", "clobber_mutex", "get_mutex", "get_mutex_id", "__init__")

        def clobber_mutex(self, *args, **kwargs):
            return self._callmethod("clobber", args=args, kwds=kwargs)

        def _callmethod(self, methodname, args=(), kwds={}):
            # Don't lock server-side mutexed methods.
            if methodname in object.__getattribute__(self, "_DONT_PROXY_MUTEX"):
                return super()._callmethod(methodname, args=args, kwds=kwds)

            # NOTE: The context management funcs __enter__ & __exit__ may be overridden, e.g., as they are for
            # Instrument. Given that proxies can't be passed to the server from client and back again whilst maintaining
            # their manager (as it can't be pickled) we need an explicit route to mutex without having to first retrieve
            # a mutex proxy - because that would require a manager for which there may not be one. So instead of using
            # ``with self.get_mutex():`` we do the following.
            is_locked = super()._callmethod("acquire")
            try:
                return super()._callmethod(methodname, args=args, kwds=kwds)
            finally:
                if is_locked:
                    super()._callmethod("release")

        def getpid(self):
            return self._manager.getpid()


class MutexedNamespaceSingleton(MutexedNamespace):

    """ A child of the above Mutex and multiprocess.managers.Namespace implemented as a singleton.

    The singleton pattern allows for namespaces to be created on the shared memory server AND be accessed from any
    client without needing a reference to its proxy but instead, just the registered name.

     Whilst multiprocessing.managers facilitate shared memory (even across networks) any object stored on the server
     is only accessible via its proxy instance. No proxy object, no access. Furthermore, the server object gets
     deleted when no longer referenced by a proxy. This means that access across processes requires you to still
     pass the proxy through from the parent to the child processes. Two ways to create something more persistent
     and more universally accessible are the following:

        1) Create a subclass of the manager with the addition of a new attribute that will be instantiated on the
           server and and accessible via registered funcs.
           As exampled by catkit.multiprocessing.SharedMemoryManager.cache_lock.
        2) Create a subclass of MutexedNamespaceSingleton using its factor method such that the registered
           TypeID will be the universal ID accessible from any client.
           As exampled by catkit.multiprocessing.SharedMemoryManager().SharedState().
    """

    instance = None

    def __new__(cls, *args, address=None, disable_shared_memory=False, **kwargs):
        if cls.instance is None:
            if (not disable_shared_memory) and (address is not None or hasattr(cls, "address")):
                # Shared usage.

                if address is None and hasattr(cls, "address"):
                    address = cls.address

                if SharedMemoryManager.is_a_server_process and address == SharedMemoryManager.server_address:
                    # This is server-side.
                    obj = super().__new__(cls, *args, **kwargs)
                else:
                    # This is client-side.
                    manager = SharedMemoryManager(address=address)
                    manager.connect()
                    obj = getattr(manager, cls.__name__)(*args, **kwargs)  # This will be a proxy.
                    # NOTE: Since cls.instance is a proxy and neither an instance nor subclass of cls, __init__() will
                    # NOT be called implicitly post __new__().
                    #assert isinstance(cls.instance, BaseProxy), type(cls.instance)
            else:
                # Local usage.
                obj = super().__new__(cls, *args, **kwargs)

            # NOTE: cls(*args, **kwargs) -> cls.__new__(cls).__init__(*args, **kwargs) when
            # isinstance(cls.__new__(cls), cls) and  cls.__new__(cls) otherwise.
            # I.e., __init__ is only implicitly called when __new__ returns an instance (or subclass) of its own class.
            # It therefore won't be called when a proxy is returned as desired.
            # However, this interferes with the singleton pattern and use of factory so we implicitly call __init__ here
            # before assigning to cls.instance, which __init__ uses as a condition on whether to be a NOOP. Using an
            # instance attribute as a NOOP flag would block if the object is locked and thus prevent even a proxy
            # retrieval of the remote object.
            if isinstance(obj, cls) or issubclass(obj.__class__, cls):
                obj.__init__(*args, **kwargs)

            # NOTE: The server mutexes its creation func from which this func is called thus mitigating the race
            # condition between ``if cls.instance is None:``, ``obj = super().__new__()``, and its assignment to
            # ``cls.instance``.
            cls.instance = obj

        return cls.instance

    def __init__(self, *args, **kwargs):
        # NOTE: We only want to initialize the singleton instance once (see notes in __new__ for more details).
        if object.__getattribute__(self, "__class__").instance is None:
            super().__init__(*args, **kwargs)

    class Proxy(MutexedNamespace.Proxy):
        pass

    @classmethod
    def factory(cls, address=None, name=None, timeout=None, new_class_dict={}):
        NewClass = type(name if name else "NewClass", (cls,), dict(instance=None,
                                                                   address=address,
                                                                   timeout=timeout,
                                                                   **new_class_dict))
        # Register the class with the server manager.
        # NOTE: Any class modification beyond this block will not be propagated to the server.
        if address:
            if name:
                # Registering classes with the server must happen before it is started.
                manager = SharedMemoryManager(address=address)
                try:
                    manager.connect()
                except ConnectionRefusedError:
                    # This is ok, the manager (probably) hasn't been started yet.
                    SharedMemoryManager.register(name, callable=NewClass, proxytype=NewClass.Proxy, create_method=True)
                else:
                    # The manager was able to connect which means that the server has already been started.
                    SharedMemoryManager.register(name, proxytype=NewClass.Proxy, create_method=True)
                finally:
                    del manager
            else:
                raise ValueError(f"Remote access requires a str name to register with {SharedMemoryManager.__qualname__}.")

        return NewClass


# class AutoProxyBase:
#     def __new__(cls, *args, **kwargs):
#         return AutoProxy(*args, **kwargs)
#
#
# class MutexedNamespaceAutoProxy(MutexedNamespace.Proxy, AutoProxyBase):
#     pass


class MutexedNamespaceAutoProxy:
    """ This is a combination of mutliprocess.managers.AutoProxy and MutexedNamespaceSingleton.Proxy
        This is proxy used by Instrument.Proxy.
    """
    # NOTE: This class allows only partial inheritance.

    # NOTE: _method_to_typeid_ needs to be in place pre-registration.
    _method_to_typeid_ = {**MutexedNamespace.Proxy._method_to_typeid_}

    def __init__(self, *args, **kwargs):
        """ Sanity checking that this isn't being called post __new__(). """
        assert False

    def __new__(cls, *args, **kwargs):
        proxy_obj = AutoProxy(*args, **kwargs)
        proxy_type = type(proxy_obj)

        proxy_obj._exposed_ = [*proxy_obj._exposed_, *MutexedNamespace.Proxy._exposed_]
        if hasattr(cls, "_exposed_"):
            proxy_obj._exposed_.extend(cls._exposed_)

        # NOTE: It's too late for this here as it needs to be done pre-registration such that it's accurate on the
        # server. However, still do so for client side correctness.
        if hasattr(proxy_obj, "_method_to_typeid_"):
            proxy_obj._method_to_typeid_.update(cls._method_to_typeid_)
        else:
            proxy_obj._method_to_typeid_ = cls._method_to_typeid_
        if hasattr(cls, "_method_to_typeid_"):
            proxy_obj._method_to_typeid_.update(cls._method_to_typeid_)

        proxy_obj._DONT_PROXY_MUTEX = MutexedNamespace.Proxy._DONT_PROXY_MUTEX

        proxy_obj.__class__.__enter__ = MutexedNamespace.Proxy.__enter__
        proxy_obj.__class__.__exit__ = MutexedNamespace.Proxy.__exit__
        proxy_obj.__class__.__delattr__ = MutexedNamespace.Proxy.__delattr__
        proxy_obj.__class__.__getattr__ = MutexedNamespace.Proxy.__getattr__
        proxy_obj.__class__.__setattr__ = MutexedNamespace.Proxy.__setattr__
        proxy_obj.__class__.__eq__ = MutexedNamespace.Proxy.__eq__
        proxy_obj.__class__.acquire = MutexedNamespace.Proxy.acquire
        proxy_obj.__class__.release = MutexedNamespace.Proxy.release
        proxy_obj.__class__.get_mutex = MutexedNamespace.Proxy.get_mutex
        proxy_obj.__class__.get_mutex_id = MutexedNamespace.Proxy.get_mutex_id

        def _callmethod(self, methodname, args=(), kwds={}):
            """ A copy of MutexedNamespace.Proxy._callmethod with added super() specification. """
            # Don't re-lock already server-side-mutexed methods.
            if methodname in object.__getattribute__(self, "_DONT_PROXY_MUTEX"):
                return super(proxy_type, self)._callmethod(methodname, args=args, kwds=kwds)

            # NOTE: See note in MutexedNamespace.Proxy._callmethod for try-except usage here.
            is_locked = super(proxy_type, self)._callmethod("acquire")
            try:
                return super(proxy_type, self)._callmethod(methodname, args=args, kwds=kwds)
            finally:
                if is_locked:
                    super(proxy_type, self)._callmethod("release")

        proxy_obj.__class__._callmethod = _callmethod

        # Inheritance.
        if cls is not MutexedNamespaceAutoProxy:
            cls_dict = cls.__dict__.copy()
            if "_exposed_" in cls_dict:
                del cls_dict["_exposed_"]
            if "_method_to_typeid_" in cls_dict:
                del cls_dict["_method_to_typeid_"]
            for key, value in cls_dict.items():
                 setattr(proxy_obj.__class__, key, value)

        return proxy_obj


class SharedMemoryManager(SyncManager):
    """
    Managers can be connected to from any process using SharedMemoryManager(address=<address>).connect().
    They therefore don't have to be passed to child processes, when created, from the parent.
    However, SyncManager.RLock() is a factory and has no functionality to return the same locks thus requiring
    locks to still be passed to the child processes, when created, from the parent.
    This class solves this issue by caching mutexes (and barriers) on the server.

    NOTE: Registrations need to occur before the server is started.

    Parameters
    ----------
    address : tuple
        A tuple of the following `(IP, port)` to start the shared server on.
    timeout : float, int
        Default timeout for mutexing access.
    own : bool
        If True, shutdown() will get called upon deletion.
    """

    # Pattern to know whether this is a server or client process: Since we're using spawn there will be an import of
    # of this module/process and thus an class def for this cls per process. Therefore, ``is_server_side`` will remain
    # False until ``_run_server()`` is called on a server process and mutates its static class attribute. However,
    # server procs may need to comm with one another so this proc may not be that of the desired server.
    # `server_address` is therefore used to disambiguate.
    is_a_server_process = False
    server_address = None
    server_pid = None

    _Server = CatkitServer

    # @classmethod
    # def _run_server(cls, registry, address, authkey, serializer, writer, initializer=None, initargs=()):
    #     """ This is run as process.target, i.e., on the server process. """
    #     # NOTE: Explicitly ref SharedMemoryManager rather than cls such that derived classes mutate their base attrs.
    #     SharedMemoryManager.is_a_server_process = True
    #     SharedMemoryManager.server_address = address
    #     SharedMemoryManager.server_pid = os.getpid()
    #     return super()._run_server(registry, address, authkey, serializer, writer, initializer=initializer,
    #                                initargs=initargs)

    def __init__(self, *args, address=None, timeout=DEFAULT_TIMEOUT, own=False, **kwargs):
        self.own = own  # Accessed by __del__ so hoist to here.

        if address is None:
            address = self.ADDRESS if hasattr(self, "ADDRESS") else DEFAULT_SHARED_MEMORY_SERVER_ADDRESS

        # NOTE: The context is set here.
        super().__init__(*args, address=address, ctx=CONTEXT, **kwargs)
        self.log = logging.getLogger()
        self.server_pid = None
        self.timeout = timeout

        self.lock_cache = None
        self.barrier_cache = None
        self.event_cache = None
        self.child_process_exceptions = None

        self.initargs = [address]

    @staticmethod
    def initializer(address):
        """ Make "initializer" a func such that multiples can be defined via class inheritance.
            NOTE: self.initargs are the args that get passed to this func by self.start() and are called by the child
                  process as initializer(*initargs), therefore, the order of self.initargs matters.
        """

        # NOTE: Explicitly ref SharedMemoryManager rather than cls such that derived classes mutate their base attrs.
        SharedMemoryManager.is_a_server_process = True
        SharedMemoryManager.server_address = address
        SharedMemoryManager.server_pid = os.getpid()

    def start(self, initializer=None, initargs=None):

        if initializer is not None or initargs is not None:
            raise TypeError("Don't pass `initializer` and `initargs` to start(). Instead define `cls.initializer` and `self.initargs`.")

        super().start(initializer=self.initializer, initargs=self.initargs)
        self.server_pid = self.getpid()
        self.log.info(f"Shared memory manager started on PID: '{self.server_pid}'")

    def shutdown(self):
        # Whilst super().shutdown() can be called multiple times, the method doesn't even exist until
        # the server is started and will thus raise an AttributeError when not.
        if self._state.value == State.STARTED:  # NOTE: ``State`` is not an enum.
            return super().shutdown()

    def __del__(self):
        if self.own:
            self.shutdown()

        if getattr(super(), "__del__", None):
            super().__del__()

    def getpid(self):
        return self._getpid()._getvalue()

    def get_exception(self, pid):
        if self.child_process_exceptions is None:
            self.child_process_exceptions = self._ExceptionCache()

        with self.child_process_exceptions:
            return self.child_process_exceptions.get(pid, None)

    def set_exception(self, pid, exception):
        if self.child_process_exceptions is None:
            self.child_process_exceptions = self._ExceptionCache()

        with self.child_process_exceptions:
            self.child_process_exceptions.update({pid: exception})

    def get_lock(self, name, timeout=None):
        if timeout is None:
            timeout = self.timeout

        if self.lock_cache is None:
            self.lock_cache = self._LockCache()

        with self.lock_cache:
            if name not in self.lock_cache:
                lock_proxy = self.Mutex(timeout=timeout)
                self.lock_cache.update({name: lock_proxy})
                return lock_proxy
            else:
                return self.lock_cache.get(name)

    def get_barrier(self, name, parties, action=None, timeout=None):
        # NOTE: Barriers are keyed only by name.
        if timeout is None:
            timeout = self.timeout

        if self.barrier_cache is None:
            self.barrier_cache = self._BarrierCache()

        with self.barrier_cache:
            if name not in self.barrier_cache:
                barrier_proxy = self.Barrier(parties=parties, action=action, timeout=timeout)
                self.barrier_cache.update({name: barrier_proxy})
                return barrier_proxy
            else:
                return self.barrier_cache[name]

    def get_event(self, name):
        if self.event_cache is None:
            self.event_cache = self._EventCache()

        with self.event_cache:
            if name not in self.event_cache:
                event_proxy = self.Event()
                self.event_cache.update({name: event_proxy})
                return event_proxy
            else:
                return self.event_cache[name]


class _PseudoMutexedDictSingleton:
    instance = None

    class _PseudoMutexedDict(UserDict):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._mutex = threading.Lock()

        def acquire(self):
            self._mutex.acquire()

        def release(self):
            self._mutex.release()

    def __new__(cls, *args, **kwargs):
        if cls.instance is None:
            cls.instance = cls._PseudoMutexedDict(*args, **kwargs)
        return cls.instance

    def __init__(self):
        assert False

    class Proxy(AcquirerProxy, DictProxy):
        pass


class _LockCache(_PseudoMutexedDictSingleton):
    instance = None


class _BarrierCache(_PseudoMutexedDictSingleton):
    instance = None


class _EventCache(_PseudoMutexedDictSingleton):
    instance = None


class _ExceptionCache(_PseudoMutexedDictSingleton):
    instance = None


# Registered types intended for internal use only.
SharedMemoryManager.register("_LockCache", callable=_LockCache, proxytype=_LockCache.Proxy, create_method=True)
SharedMemoryManager.register("_BarrierCache", callable=_BarrierCache, proxytype=_BarrierCache.Proxy, create_method=True)
SharedMemoryManager.register("_EventCache", callable=_EventCache, proxytype=_EventCache.Proxy, create_method=True)
SharedMemoryManager.register("_ExceptionCache", callable=_ExceptionCache, proxytype=_ExceptionCache.Proxy, create_method=True)
SharedMemoryManager.register("_getpid", callable=os.getpid, proxytype=ValueProxy)

# Register shared types.
SharedMemoryManager.register("Mutex", callable=Mutex, proxytype=Mutex.Proxy, create_method=True)
SharedMemoryManager.register("MutexedNamespace", callable=MutexedNamespace, proxytype=MutexedNamespace.Proxy, create_method=True)


# Register proxies.
SharedMemoryManager.register("MutexProxy", proxytype=Mutex.Proxy, create_method=False)
SharedMemoryManager.register("MutexedNamespaceAutoProxy", proxytype=MutexedNamespaceAutoProxy, create_method=False)
SharedMemoryManager.register("BarrierProxy", proxytype=BarrierProxy, create_method=False)
SharedMemoryManager.register("EventProxy", proxytype=EventProxy, create_method=False)


# Types used for CI testing.
SHARED_STATE_ADDRESS = ("127.0.0.1", 7000)
SharedState = MutexedNamespaceSingleton.factory(address=SHARED_STATE_ADDRESS, name="SharedState", timeout=2)
