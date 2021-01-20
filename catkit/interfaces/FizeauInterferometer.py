from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument

"""Abstract base class for all Fizeau Interferometers. Implementations of this class also become context managers."""


class FizeauInterferometer(Instrument, ABC):
    @abstractmethod
    def take_measurement(self, num_frames, filename):
        """Takes exposures and should be able to save fits and simply return the image data."""
