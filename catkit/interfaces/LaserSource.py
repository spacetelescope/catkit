from abc import abstractmethod

from catkit.interfaces.Instrument import Instrument

"""Interface for a laser source."""


class LaserSource(Instrument):
    @abstractmethod
    def set_current(self, value):
        """Sets the current"""

    @abstractmethod
    def get_current(self):
        """Returns the value of the laser's current."""

    @property
    def current(self):
        return self.get_current()
