from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument


class TemperatureHumiditySensor(Instrument, ABC):
    
    @abstractmethod
    def get_temp_humidity(self):
        """ Measures and returns temperature and humidity. """

    @abstractmethod
    def get_temp(self, channel):
        """ Measures and returns temperature and humidity. """

    @abstractmethod
    def get_humidity(self):
        """ Measures and returns humidity. """
