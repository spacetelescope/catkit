from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument


class DataAcquisitionDevice(Instrument, ABC):

    @abstractmethod
    def read_multichannel(self):
        """ Reads voltages from all channels. """

    @abstractmethod
    def read_singlechannel(self, channel):
        """ Reads voltages from a specific single channel. """

    @abstractmethod
    def write_multichannel(self, values):
        """ Writes voltages to all channels. """

    @abstractmethod
    def write_singlechannel(self, value, channel):
        """ Writes voltages to a specific single channel. """
