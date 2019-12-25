from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument
"""Interface for a two state flip motor."""


class FlipMotor(Instrument, ABC):

    @abstractmethod
    def move_to_position1(self):
        """Implements a move to position 1."""

    @abstractmethod
    def move_to_position2(self):
        """Implements a move to position 2."""
