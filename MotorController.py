from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
from abc import ABCMeta, abstractmethod

"""Interface for a motor controller."""


class MotorController(object):
    __metaclass__ = ABCMeta

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with the DM and sets class attributes for 'config_id' and 'dm'."""
        self.config_id = config_id
        self.socket_id = None
        self.motor_controller = self.initialize(*args, **kwargs)
        print("Initialized Motor Controller " + config_id)

    # Implementing context manager.
    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()
        self.motor_controller = None
        print("Safely closed connection to Motor Controller " + self.config_id)

    # Abstract Methods.
    @abstractmethod
    def initialize(self, *args, **kwargs):
        """Creates an instance of the controller library and opens a connection."""

    @abstractmethod
    def close(self):
        """Close dm connection safely."""

    @abstractmethod
    def absolute_move(self, motor_id, position):
        """Implements an absolute move"""

    @abstractmethod
    def relative_move(self, motor_id, distance):
        """Implements an absolute move"""

    @abstractmethod
    def get_position(self, motor_id):
        """Returns the current position of a motor."""
