from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
from abc import *

"""Interface for a laser source."""


class LaserSource(object):
    __metaclass__ = ABCMeta

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with the laser source and sets class attributes for 'config_id'"""
        self.config_id = config_id
        self.laser = self.initialize(self, *args, **kwargs)
        print("Opened connection to laser source " + config_id)

    # Implementing context manager.
    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()
        self.laser = None
        print("Safely closed connection to laser source " + self.config_id)

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
