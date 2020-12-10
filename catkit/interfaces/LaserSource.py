import logging
from abc import ABC, abstractmethod

"""Interface for a laser source."""


class LaserSource(ABC):
    log = logging.getLogger()

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with the laser source and sets class attributes for 'config_id'"""
        self.config_id = config_id
        self._keep_alive = False
        self.instrument = None

        # Connect.
        self.laser = self.initialize(*args, **kwargs)
        self.instrument = self.laser
        self.log.info("Opened connection to laser source " + config_id)

    # Implementing context manager.
    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        try:
            if not self._keep_alive:
                try:
                    if self.instrument:
                        self.close()
                finally:
                    self.laser = None
                    self.instrument = None
                self.log.info("Safely closed connection to laser source " + self.config_id)
        finally:
            # Reset, single use basis only.
            self._keep_alive = False

    # Abstract Methods.
    @abstractmethod
    def initialize(self, *args, **kwargs):
        """Creates an instance of the laser source dll and sets default current."""

    @abstractmethod
    def close(self):
        """Close laser source connection safely."""

    @abstractmethod
    def set_current(self, value):
        """Sets the current"""

    @abstractmethod
    def get_current(self):
        """Returns the value of the laser's current."""
