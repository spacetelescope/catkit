from abc import *


class Camera(object):
    __metaclass__ = ABCMeta

    def __init__(self, config_id, *args, **kwargs):
        print("_init_")
        self.config_id = config_id
        self.camera = self.initialize(self, *args, **kwargs)

    # Implementing context manager.
    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, type, value, traceback):
        print("_exit_")
        self.close()

    @abstractmethod
    def initialize(self, *args, **kwargs):
        """Opens connection with camera and returns camera object."""

    @abstractmethod
    def close(self):
        """Close camera connection"""

    @abstractmethod
    def take_exposures_fits(self, exposure_length, num_exposures, path, filename, *args, **kwargs):
        """Takes exposures and saves as FITS files, and returns list of file paths."""

    @abstractmethod
    def take_exposures_data(self, exposure_length, num_exposures, *args, **kwargs):
        """Takes exposures and returns list of numpy arrays."""
