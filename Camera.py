from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from abc import *

"""Abstract base class for all cameras. Implementations of this class also become context managers."""


class Camera(object):
    __metaclass__ = ABCMeta

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with camera sets class attributes for 'config_id' and 'camera'."""
        self.config_id = config_id
        self.camera = self.initialize(self, *args, **kwargs)
        print("Opened connection to camera: " + self.config_id)

    # Implementing context manager.
    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()
        self.camera = None
        print("Safely closed camera: " + self.config_id)

    # Abstract Methods.
    @abstractmethod
    def initialize(self, *args, **kwargs):
        """Opens connection with camera and returns the camera manufacturer specific object."""

    @abstractmethod
    def close(self):
        """Close camera connection."""

    @abstractmethod
    def take_exposures_fits(self, exposure_length, num_exposures, path, filename, *args, **kwargs):
        """Takes exposures and saves as FITS files, and returns list of file paths."""

    @abstractmethod
    def take_exposures_data(self, exposure_length, num_exposures, *args, **kwargs):
        """Takes exposures and returns list of numpy arrays."""
