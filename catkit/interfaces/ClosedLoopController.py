from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument


class ClosedLoopController(Instrument, ABC):
    """ Interface class for a closed loop controller. """

    @abstractmethod
    def set_closed_loop(self, active=True):
        """ Activate closed-loop control on all channels. """

    @abstractmethod
    def get(self, var, channel):
        """ Get a command from the closed-loop controller. """

    @abstractmethod
    def set(self, var, channel, value):
        """ Set a command on the closed-loop controller. """

    @abstractmethod
    def set_and_check(self, parameter, channel, value):
        """ Set a command on the closed-loop controller and the get and checl that it was correctly set. """

    @abstractmethod
    def get_status(self, channel):
        """ Gets the status of the closed-loop controller. """

