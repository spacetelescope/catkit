from abc import ABC, abstractmethod
import inspect
import logging

_not_permitted_error = "Positional args are not permitted. Call with explicit keyword args only.\n"\
                       "E.g., def func(a, b) called as func(1, 2) -> func(a=1, b=2)"


def call_with_correct_args(func, **kwargs):
    """ Extract from kwargs only those args required by func."""
    signature = inspect.getfullargspec(func)
    func_kwargs = {arg: kwargs[arg] for arg in kwargs if arg in signature.args or arg in signature.kwonlyargs}
    return func(**func_kwargs)


class Instrument(ABC):
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

    def __init__(self, config_id, *not_permitted, **kwargs):
        if not_permitted:
            raise TypeError(_not_permitted_error)
        self.log = logging.getLogger(f"{self.__module__}.{self.__class__.__qualname__}")
        self.instrument = None  # Make local, intentionally shadowing class member.
        self.__keep_alive = False  # Back door - DO NOT USE!!!
        self.config_id = config_id
        self.socket_id = None  # Legacy - we will remove at some point.
        call_with_correct_args(self.initialize, **kwargs)  # This should NOT open a connection!
        self.log.info("Initialized '{}' (but connection is not open)".format(config_id))

    # Context manager Enter function, gets called automatically when the "with" statement is used.
    def __enter__(self):
        # Attempt to force the use of ``with`` by only opening here and not in __init__().
        self.__open()
        return self

    # Context manager Exit function, gets called automatically the code exits the context of the "with" statement.
    def __exit__(self, exception_type, exception_value, exception_traceback):
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
        try:
            self.instrument = self._open()
            self.log.info("Opened connection to '{}'".format(self.config_id))
        except Exception:
            self.__close()
            raise

    def __close(self):
        # __func() can't be overridden without also overriding those that call it.
        try:
            if self.instrument:
                self._close()
                self.log.info("Safely closed connection to '{}'".format(self.config_id))
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


class SimInstrument(Instrument, ABC):
    """To be inherited by simulated versions of the actual hardware classes."""
    def __init__(self, *not_permitted, **kwargs):
        if not_permitted:
            raise TypeError(_not_permitted_error)

        self.instrument_lib = call_with_correct_args(self.instrument_lib, **kwargs)
        # Pass all **kwargs through as ``__init__()`` calls ``initialize()`` as ``call_with_correct_args(self.initialize, **kwargs)``
        return super().__init__(**kwargs)
