from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument


class FlipMotor(Instrument, ABC):
    """ Interface for a two state flip motor. """

    @abstractmethod
    def move_to_position(self, position_number):
        """ Calls move_to_position<position_number>. """

    @abstractmethod
    def move_to_position1(self):
        """ Implements a move to position 1. """

    @abstractmethod
    def move_to_position2(self):
        """ Implements a move to position 2. """
