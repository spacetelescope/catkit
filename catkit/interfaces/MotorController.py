from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument

"""Interface for a motor controller."""


class MotorController(Instrument, ABC):

    @abstractmethod
    def absolute_move(self, motor_id, position):
        """Implements an absolute move"""

    @abstractmethod
    def relative_move(self, motor_id, distance):
        """Implements an absolute move"""

    @abstractmethod
    def get_position(self, motor_id):
        """Returns the current position of a motor."""
