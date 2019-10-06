from abc import ABC, abstractmethod
import logging


class Instrument(ABC):
    """Generic interface to any instrument, implements a context manager."""
    log = logging.getLogger(__name__)

    instrument_lib = None

    def __new__(cls, config_id, *args, **kwargs):
        return super().__new__(cls)

    def __init__(self, config_id, *args, **kwargs):
        self.instrument = None
        self.__keep_alive = False  # Back door - DO NOT USE!!!
        self.config_id = config_id
        self.socket_id = None  # Legacy - we will remove at some point.
        self.initialize(*args, **kwargs)  # This should NOT open a connection!
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
                self.close()
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
    def close(self):
        """Close connection to self.instrument. Must be a NOOP if self.instrument is None"""
