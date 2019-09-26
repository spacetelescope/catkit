import logging
from abc import ABC, abstractmethod

"""Interface for a laser source."""


class LaserSource(ABC):
    log = logging.getLogger()

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with the laser source and sets class attributes for 'config_id'"""
        self.config_id = config_id
        self.laser = self.initialize(*args, **kwargs)
        self.log.info("Opened connection to laser source " + config_id)

    # Implementing context manager.
    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()
        self.laser = None
        self.log.info("Safely closed connection to laser source " + self.config_id)

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
