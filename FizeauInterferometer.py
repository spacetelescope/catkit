from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from abc import ABCMeta, abstractmethod

"""Abstract base class for all Fizeau Interferometers. Implementations of this class also become context managers."""


class FizeauInterferometer(object):
    __metaclass__ = ABCMeta

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with camera sets class attributes for 'config_id'"""
        self.config_id = config_id
        self.interferometer = self.initialize(self, *args, **kwargs)
        print("Opened connection to Fizeau Interferometer: " + self.config_id)

    # Implementing context manager.
    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()
        self.interferometer = None
        print("Safely closed Fizeau Interferometer: " + self.config_id)

    # Abstract Methods.
    @abstractmethod
    def initialize(self, *args, **kwargs):
        """Opens connection with interferometer and returns the camera manufacturer specific object."""

    @abstractmethod
    def close(self):
        """Close interferometer connection."""

    @abstractmethod
    def take_measurement(self, num_frames, path, filename, *args, **kwargs):
        """Takes exposures and should be able to save fits and simply return the image data."""
