from collections import namedtuple
import os
import threading

# NOTE: "multiprocess" is a 3rd party package and not Python's own "multiprocessing".
# https://github.com/uqfoundation/multiprocess is a fork of multiprocessing that uses "dill" instead of "pickle".
from multiprocess import get_context, get_logger, TimeoutError
from multiprocess.managers import AcquirerProxy, BarrierProxy, Namespace, NamespaceProxy, State, \
    SyncManager, ValueProxy


DEFAULT_TIMEOUT = 60
DEFAULT_SHARED_MEMORY_SERVER_ADDRESS = ("127.0.0.1", 6000)  # IP, port.

CONTEXT_METHOD = "spawn"
CONTEXT = get_context(CONTEXT_METHOD)


class Process(CONTEXT.Process):
    def run(self):
        """ Catch exception on child process and save in shared memory manager for parent to read.
            This is executed on the child process.
        """
        try:
            super().run()
        except Exception as error:
            try:  # Manager may not have been started.
                manager = SharedMemoryManager()
                manager.connect()
                manager.set_exception(self.pid, error)
            finally:
                raise error

    def join(self):
        """ Join and raise saved exception if one occurred.
            This is executed on the parent process.
        """
        super().join()
        if not self.exitcode:
            return

        exception = Exception(f"Child process ('{self.name}' with pid: '{self.pid}') exited with non-zero exitcode: '{self.exitcode}'")

        child_exception = None
        try:  # Manager may not have been started.
            manager = SharedMemoryManager()
            manager.connect()
            exception = manager.get_exception(self.pid)
        except Exception:
             pass

        if child_exception:
            raise exception from child_exception
        else:
            raise exception


class Mutex:
    """ A container for a shared re-entrant lock.

        NOTE: For this to be actually shared it is subsequently registered with
        catkit.multirocessing.SharedMemoryManager and must be instantiated from a running/connected instance of
        catkit.multirocessing.SharedMemoryManager.
    """

    def __init__(self, *args, lock=None, timeout=DEFAULT_TIMEOUT, **kwargs):
        super().__init__(*args, **kwargs)
        lock = threading.RLock() if lock is None else lock
        self.lock = lock.lock if isinstance(lock, Mutex) else lock
        self.timeout = timeout

    def acquire(self, timeout=None, raise_on_fail=True):
        """
            https://docs.python.org/3/library/multiprocessing.html#multiprocessing.RLock
            The parent semantics for `timeout=None` := timeout=infinity. We have zero use case for this and, instead,
            will use `self.timeout` if `timeout is None`.
        """
        if timeout is None:
            timeout = self.timeout

        locked = self.lock.acquire(timeout=timeout)
        if raise_on_fail and not locked:
            raise TimeoutError(f"Failed to acquire lock after {timeout}s")
        return locked

    def release(self):
        return self.lock.release()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.release()

    class Proxy(AcquirerProxy):
        def acquire(self, *args, **kwargs):
            return self._callmethod('acquire', args, kwargs)  # Don't unpack.


class MutexedSingletonNamespace:

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
        2) Create a subclass of MutexedSingletonNamespace and register it such that the registered
           TypeID will be the universal ID accessible from any client.
           As exampled by catkit.multiprocessing.SharedMemoryManager().shared_state().
    """

    instance = None

    # Namespace.__init__() takes only **kwargs so we're forced to use this inheritance order (not that it would matter).
    class _MutexedSingletonNamespace(Mutex, Namespace):
        pass

    def __new__(cls, *args, **kwargs):
        if not cls.instance:
            cls.instance = cls._MutexedSingletonNamespace(*args, **kwargs)
        return cls.instance

    # __getattr__ & __setattr__ should explicitly NOT be mutexed as reentrant locks are only reentrant from the same
    # process and these will get executed server-side, which would cause a timeout/deadlock.
    def __getattr__(self, name):
        return self.instance.__getattribute__(name)

    def __setattr__(self, name, value):
        return object.__setattr__(self.instance, name, value)

    # Proxy (client-side) access needs to be mutexed though the mutex doesn't belong to the proxy instance but the
    # server-side referent. The manager mutexes access on the server, however, we wish to expose a mutex to the client
    # such that multiple accesses can be mutexed.
    class Proxy(Mutex.Proxy, NamespaceProxy):
        _exposed_ = ('__getattribute__', '__setattr__', '__delattr__', 'acquire', 'release')

        # Copied from NamespaceProxy (with added mutex).
        def __getattr__(self, key):
            if key[0] == '_':
                return object.__getattribute__(self, key)
            try:
                locked = None
                locked = object.__getattribute__(self, "__enter__")()
                callmethod = object.__getattribute__(self, '_callmethod')
                return callmethod('__getattribute__', (key,))
            finally:
                if locked:
                    object.__getattribute__(self, "__exit__")(None, None, None)

        def __setattr__(self, key, value):
            if key[0] == '_':
                return object.__setattr__(self, key, value)
            try:
                locked = None
                locked = object.__getattribute__(self, "__enter__")()
                callmethod = object.__getattribute__(self, '_callmethod')
                return callmethod('__setattr__', (key, value))
            finally:
                if locked:
                    object.__getattribute__(self, "__exit__")(None, None, None)

        def __delattr__(self, key):
            if key[0] == '_':
                return object.__delattr__(self, key)
            try:
                locked = None
                locked = object.__getattribute__(self, "__enter__")()
                callmethod = object.__getattribute__(self, '_callmethod')
                return callmethod('__delattr__', (key,))
            finally:
                if locked:
                    object.__getattribute__(self, "__exit__")(None, None, None)


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

    def __init__(self, *args, address=DEFAULT_SHARED_MEMORY_SERVER_ADDRESS, timeout=DEFAULT_TIMEOUT, own=False, **kwargs):
        super().__init__(*args, address=address, **kwargs)
        self.log = get_logger()
        self.server_pid = None
        self.own = own

        # Server-side non-shared non-reentrant lock to protect against any possible server-side threading.
        self.master_lock = Mutex(lock=threading.Lock(), timeout=timeout)

        self.lock_cache = {}  # Cache for all locks (local dummy - don't access directly).
        self.barrier_cache = {}  # Cache for all barriers (local dummy - don't access directly).
        self.child_process_exceptions = {}  # Used to pass exceptions back to parent.

        # Nothing is stored in the above (local) instances, they are copied to the server and must then be accessed by
        # the following registered funcs.

        def get_lock(name, timeout=DEFAULT_TIMEOUT):
            # NOTE: This is registered below and will get executed server-side.
            with self.master_lock:
                if name not in self.lock_cache:
                    self.lock_cache.update({name: Mutex(lock=threading.RLock(), timeout=timeout)})
                return self.lock_cache.get(name)

        def get_barrier(name, parties, action=None, timeout=DEFAULT_TIMEOUT):
            # NOTE: This is registered below and will get executed server-side.
            with self.master_lock:
                if name not in self.barrier_cache:
                    self.barrier_cache.update({name: threading.Barrier(parties=parties,
                                                                       action=action,
                                                                       timeout=timeout)})
                return self.barrier_cache.get(name)

        # Registered funcs get executed server side.
        self.register("_getpid", callable=os.getpid, proxytype=ValueProxy)  # This will return the PID of the server.
        self.register("get_lock", callable=get_lock, proxytype=Mutex.Proxy)
        self.register("get_barrier", callable=get_barrier, proxytype=BarrierProxy)

        def set_exception(pid, exception):
            self.child_process_exceptions[pid] = exception

        self.register("set_exception", callable=set_exception)
        self.register("_get_exception", callable=lambda pid: self.child_process_exceptions.get(pid), proxytype=ValueProxy)

    def getpid(self):
        return self._getpid()._getvalue()

    def get_exception(self, pid):
        return self._get_exception(pid)._getvalue()

    def start(self, *args, **kwargs):
        ret = super().start(*args, **kwargs)
        self.server_pid = self.getpid()
        self.log.info(f"Shared memory manager started on PID: '{self.server_pid}'")
        return ret

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


SharedMemoryManager.register("Mutex", callable=Mutex, proxytype=Mutex.Proxy)


class SharedState(MutexedSingletonNamespace):
    pass


# Then make the above namespace object `SharedState` accessible from any client via
# `SharedMemoryManager().connect().SharedState()`:
SharedMemoryManager.register("SharedState", callable=SharedState, proxytype=SharedState.Proxy)
