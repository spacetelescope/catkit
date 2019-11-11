from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument
"""Abstract base class for all cameras. Implementations of this class also become context managers."""


class Camera(Instrument, ABC):

    @abstractmethod
    def take_exposures(self, exposure_length, num_exposures, path=None, filename=None, *args, **kwargs):
        """Takes exposures and should be able to save fits and simply return the image data."""

