from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument


class ClosedLoopController(Instrument, ABC):
    """ Interface class for a closed loop controller. """


    @abstractmethod
    def command(self, var, channel, value):
        """Sends a command to the closed-loop controller. """

    @abstractmethod
    def get_status(self, channel):
        """Gets the status of the closed-loop controller."""

