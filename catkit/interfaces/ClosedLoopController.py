from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument


class ClosedLoopController(Instrument, ABC):
    """ Interface class for a closed loop controller. """


    @abstractmethod
    def command(self, cmd_key, channel, value):
        """Sends a command to the close loop. """

    @abstractmethod
    def get_status(self, channel):
        """Gets the status of the controller."""

