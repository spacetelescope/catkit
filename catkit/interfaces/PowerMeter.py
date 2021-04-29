from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument


class PowerMeter(Instrument, ABC):

    @abstractmethod
    def get_power(self):
        """ Measures and returns power. """
