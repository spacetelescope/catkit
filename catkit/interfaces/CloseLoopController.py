from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument


class CloseLoopController(Instrument, ABC):
    """ Interface class for a close loop controller. """


    @abstractmethod
    def command(self, cmd_key, channel, value):
        """Sends a command to the close loop. """

    @abstractmethod
    def get_status(self, channel):
        """Gets the status of the controller."""

