from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument
"""Abstract base class for all cameras. Implementations of this class also become context managers."""


class Camera(Instrument, ABC):

    @abstractmethod
    def take_exposures(self, exposure_time, num_exposures, path=None, filename=None, *args, **kwargs):
        """Takes exposures and should be able to save fits and simply return the image data."""

    @abstractmethod
    def stream_exposures(self, exposure_time, num_exposures, *args, **kwargs):
        """ Take a stream of exposures and yield individual images (ie. a generator)."""
