from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument


class RemotePowerSwitch(Instrument, ABC):
    """ Interface for remote controlled power switch. """

    @abstractmethod
    def switch(self, outlet_id, on, all=False):
        """ Turn on/off all/individual outlet(s). """

    @abstractmethod
    def turn_on(self, outlet_id):
        """ Turn on an individual outlet. """

    @abstractmethod
    def turn_off(self, outlet_id):
        """
        Turn off an individual outlet.
        """

    @abstractmethod
    def all_on(self):
        """
        Turn on all outlets.
        """

    @abstractmethod
    def all_off(self):
        """
        Turn off all outlets.
        """
