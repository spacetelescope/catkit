from abc import ABC, abstractmethod
import inspect
import logging
import threading


from multiprocessing.managers import AcquirerProxy

from catkit.multiprocessing import DEFAULT_TIMEOUT, Mutex, MutexedNamespaceAutoProxy, MutexedNamespace, SharedMemoryManager

_not_permitted_error = "Positional args are not permitted. Call with explicit keyword args only.\n"\
                       "E.g., def func(a, b) called as func(1, 2) -> func(a=1, b=2)"


def call_with_correct_args(func, object=None, kwargs_to_assign=None, **kwargs):
    """ Extract from kwargs only those args required by func.
        If args in `kwargs_to_assign` or `kwargs` don't belong to func's signature assign them to object.__dict__.
    """
    signature = inspect.getfullargspec(func)
    func_kwargs = {}
    if not object or kwargs_to_assign:
        # Parse **kwargs. If object and not kwargs_to_assign is dealt with in `if object`.
        func_kwargs.update({arg: kwargs[arg] for arg in kwargs if arg in signature.args or arg in signature.kwonlyargs})

    if object:  # This assumes that func is an method of object, i.e., __init__.
        # kwargs_to_assign can be an explicit dict of kwargs to assign or any and all in kwargs.
        _kwargs_to_assign = kwargs_to_assign if kwargs_to_assign else kwargs
        for key, value in _kwargs_to_assign.items():
            if key in signature.args or key in signature.kwonlyargs:
                func_kwargs[key] = value
            else:
                object.__dict__[key] = value
    return func(**func_kwargs)


class InstrumentBaseProxy(AcquirerProxy):
    """ self._callmethod() isn't mutexed.

        WARNING: This is NOT implicitly mutexed on a per call basis and is therefore not implicitly thread safe.
                 To make thread safe the user must suitably call ``self.acquire()`` from the client - don't forget
                 to call ``release()`` when done. Alternatively, context management can be used as the following
                 ``with self.get_mutex():``.

        NOTE: The child class must define ``_method_to_typeid_`` such that "__enter__" returns the correct
        registered child proxy.

        E.g.,

        ``_method_to_typeid_ = {"__enter__": "registered_name_of_child_proxy", **InstrumentBaseProxy._method_to_typeid_}``
    """
    # NOTE: We inherit from AcquirerProxy and not Mutex.Proxy to avoid conditionals in NamespaceProxy (which Mutex.Proxy
    # is a child of). However, we still want the functionality of Mutex.Proxy.get_mutex().

    _method_to_typeid_ = {"get_mutex": "MutexProxy"}

    def get_mutex(self):
        return self._callmethod("get_mutex")

    def is_open(self):
        return self._callmethod("is_open")

    # AcquirerProxy.__enter__ calls acquire. We want to override their semantics to an open & close context.
    # NOTE: If accessing via catkit.testbed.caching.DeviceCacheEnum, this is reverted back to acquire semantics.
    # E.g.,
    #      DeviceCacheEnum.MEMBER.__enter__() => Instrument.acquire()
    #      DeviceCacheEnum.MEMBER().__enter__() => Instrument.__enter__()
    def __enter__(self, *args, **kwargs):
        return self._callmethod("__enter__", args=args, kwds=kwargs)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # NOTE: Tracebacks can't be pickled (currently), so pass exc_tb as None instead.
        return self._callmethod("__exit__", args=(exc_type, exc_val, None))


class Service:

    def __init__(self, disable=False):
        self.log = logging.getLogger()

        self.service_thread = None
        self.exception_handler = None

        self.pause_event = None
        self.un_pause_event = None
        self.stop_event = None

        if not disable:
            self.exception_handler = SharedMemoryManager(...)
            self.pause_event = self.exception_handler.get_event(...)
            self.un_pause_event = self.exception_handler.get_event(...)
            self.stop_event = self.exception_handler.get_event(...)

    def run_service(self):
        self.service_thread = threading.Thread(target=self.serve, daemon=False)
        self.service_thread.start()
        self.log.info(f"Running {self.__class__.__name__} as a service.")

    def stop_service(self, timeout=DEFAULT_TIMEOUT):
        if self.service_thread and self.service_thread.is_alive():
            # Set events to stop service loop.
            self.stop_event.set()
            self.un_pause_event.set()

            self.log.info(f"Waiting for {self.__class__.__name__} service to stop...")
            self.service_thread.join(timeout=timeout)

            # Did the service stop or did it timeout?
            if self.service_thread.is_alive():
                # TODO: Should service_thread be daemonic? If so, I think there would be enough of a window for comms
                # to get corrupted, from the forced thread kill, which could cause subsequent closure issues thus
                # presenting as a device safety concern, e.g., not being able to flatten the boston.
                TimeoutError(f"{self.__class__.__name__} service failed to stop within {timeout}s.")

    def serve(self):
        self.initializer()
        while not self.stop_event.is_set():
            if self.pause_event.is_set():

                # Pause
                self.un_pause_event.wait()

                # Reset
                self.un_pause_event.clear()
                self.pause_event.clear()
                # Check stop_event again.

                if self.stop_event.is_set():
                    break

            self.server_loop()  # NOTE: We could even abstract the stream interaction from this abstract method such
                                # that anyone writing/adding a new device only has to give the func to acquire/send
                                # the data.
                                # Note: a flag might then be needed to disambiguate between devices that push to
                                # streams (e.g., cams) from those that pull (e.g., DMs).

    def initializer(self, *args, **kwargs):
        ...

    @abstractmethod
    def server_loop(self, *args, **kwargs):
        ...


class Instrument(Service, MutexedNamespace, ABC):
    """ This is the abstract base class intended to to be inherited and ultimately implemented
    by all of our hardware classes (actual or emulated/simulated).
    This is not pure and is not intended to be, such that restrictions can be imposed to safely
    and adequately control access to the underlying hardware connections.

    Use pattern:
     * `initialize()` is called by `__init__()`, is not assigned to anything and MUST NEVER open
        a connection to the hardware.
     * `_open()` MUST return an object connected to the instrument,
        that can be assigned to self.instrument. It is hidden as it should not be called.
        Connections should only be opened when context managed using the `with` statement.
     * `self.instrument` holds the ref to the connection object.
     * `self.instrument_lib` points to the connection library, actual or emulated.
     * No methods should be overridden other than those abstract by implementing them.
     * The only other restriction is that instantiation should be called with explicit keyword args,
       and not implicit positionals. Positionals are ok in the func signature, just not the call to it (binding).
    """

    instrument_lib = None

    # Initialize this here such that it always exists for __del__().
    # Is an issue otherwise if an  __init__() raises before self.instrument = None is set.
    instrument = None

    def __init__(self, config_id, *not_permitted, run_as_service=False, **kwargs):
        if not_permitted:
            raise TypeError(_not_permitted_error)

        self.run_as_service = run_as_service
        self._context_counter = 0  # Used to count __enter__ & __exit__ paired usage.
        self.log = logging.getLogger()
        self.instrument = None  # Make local, intentionally shadowing class member.
        self.__keep_alive = False  # Back door - DO NOT USE!!!
        self.config_id = config_id
        self.socket_id = None  # Legacy - we will remove at some point.
        call_with_correct_args(self.initialize, **kwargs)  # This should NOT open a connection!
        self.log.info("Initialized '{}' (but connection is not open)".format(config_id))

    # Context manager Enter function, gets called automatically when the "with" statement is used.
    # Only the outer most `with` does anything, all others are NOOPs.
    def __enter__(self):
        if self._context_counter == 0:
            # Attempt to force the use of ``with`` by only opening here and not in __init__().
            self.__open()

        self._context_counter += 1
        return self

    # Context manager Exit function, gets called automatically the code exits the context of the "with" statement.
    # Only the outer most `with` does anything, all others are NOOPs.
    def __exit__(self, exception_type, exception_value, exception_traceback):
        self._context_counter -= 1
        if self._context_counter < 1:
            try:
                if not self.__keep_alive:
                    self.__close()
            finally:
                # Reset, single use basis only.
                self.__keep_alive = False

    def __del__(self):
        self.__close()

    def __open(self):
        # __func() can't be overridden without also overriding those that call it.

        # If instrument is already opened, don't create multiple connections.
        if self.instrument:
            return

        try:
            self.instrument = self._open()
            self.log.info("Opened connection to '{}'".format(self.config_id))

            if self.run_as_service:
                self.run_service()
        except Exception:
            #self.__close()
            raise

    def _forced_safe_close(self):
        """ Bypass mutex and close device.

            It's possible for a client mutex to deadlock or just fail to release thus blocking all access to the
            device, including the ability to close it - which can not happen. To resolve this we hijack the mutex by
            replacing it with another and then close as normal.

            NOTE: This can cause an original ``release()`` to raise since the underlying mutex has changed. However,
            for this occur something has already gone wrong and closing the device is more important than worrying about
            exceptions amongst exceptions.
        """
        mutex = Mutex()
        with mutex:
            object.__setattr__(self, "_catkit_mutex", mutex)
            return self.__close()

    def __close(self):
        # __func() can't be overridden without also overriding those that call it.
        try:
            if self.run_as_service:
                self.stop_service()

            if self.instrument:
                try:
                    self._close()
                    self.log.info("Safely closed connection to '{}'".format(self.config_id))
                except Exception:
                    if not self.run_as_service:
                        raise

                    # We may have tried closing mid service loop which caused the close to fail.
                    self.instrument = self._open()
                    self._close()
        finally:
            self.instrument = None

    @abstractmethod
    def initialize(self, *args, **kwargs):
        """Implement this function to initialize class BUT MUST NEVER open a connection to the instrument."""

    @abstractmethod
    def _open(self):
        """Open connection. MUST return an object connected to the instrument,
        that can be assigned to self.instrument."""

    @abstractmethod
    def _close(self):
        """Close connection to self.instrument. Must be a NOOP if self.instrument is None"""

    def get_instrument_lib(self):
        return self.instrument_lib

    def is_open(self):
        return self.instrument is not None

    class Proxy(MutexedNamespaceAutoProxy):

        _method_to_typeid_ = {"__enter__": "InstrumentProxy",
                              "get_instrument_lib": "MutexedNamespaceAutoProxy",
                              **MutexedNamespaceAutoProxy._method_to_typeid_}

        # MutexedNamespaceAutoProxy.__enter__ calls acquire rather than letting the base __enter__ call acquire.
        # We thus want to revert their proxy semantics to an open & close context.
        # NOTE: Ideally we would just inherit from InstrumentBaseProxy, however, MutexedNamespaceAutoProxy doesn't
        # support this.
        __enter__ = InstrumentBaseProxy.__enter__
        __exit__ = InstrumentBaseProxy.__exit__

        def get_instrument_lib(self):
            return self._callmethod("get_instrument_lib")

        @property
        def instrument_lib(self):
            return self.get_instrument_lib()

        @property
        def instrument(self):
            raise AttributeError("The attribute `instrument` is not accessible from a client.")


SharedMemoryManager.register("InstrumentProxy", proxytype=Instrument.Proxy, create_method=False)


class SimInstrument(Instrument, ABC):
    """To be inherited by simulated versions of the actual hardware classes."""
    def __init__(self, *not_permitted, **kwargs):
        if not_permitted:
            raise TypeError(_not_permitted_error)

        self.instrument_lib = call_with_correct_args(self.instrument_lib, **kwargs)
        # Pass all **kwargs through as ``__init__()`` calls ``initialize()`` as ``call_with_correct_args(self.initialize, **kwargs)``
        return super().__init__(**kwargs)
