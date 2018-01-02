from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
from abc import ABCMeta, abstractmethod
import logging

"""Interface for a two state flip motor."""


class FlipMotor(object):
    __metaclass__ = ABCMeta
    log = logging.getLogger(__name__)

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with the motor controller and sets class attributes for 'config_id' and 'motor'."""
        self.config_id = config_id
        self.serial = None
        self.motor = self.initialize(*args, **kwargs)
        self.log.info("Opened connection to flip motor " + config_id)

    # Implementing context manager.
    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()
        self.motor = None
        self.log.info("Safely closed connection to flip motor " + self.config_id)

    # Abstract Methods.
    @abstractmethod
    def initialize(self, *args, **kwargs):
        """Creates an instance of the controller library and opens a connection."""

    @abstractmethod
    def close(self):
        """Close motor controller connection safely."""

    @abstractmethod
    def move_to_position1(self):
        """Implements a move to position 1."""

    @abstractmethod
    def move_to_position2(self):
        """Implements a move to position 2."""
