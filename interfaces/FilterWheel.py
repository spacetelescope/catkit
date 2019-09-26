import logging

from abc import abstractmethod
from hicat.interfaces.Instrument import Instrument

"""Abstract base class for filter wheels."""


class FilterWheel(Instrument):
    log = logging.getLogger(__name__)

    @abstractmethod
    def get_position(self):
        """Query filter wheel, and return a value that represents the current filter position."""

    @abstractmethod
    def set_position(self, new_position):
        """Set the new position and return a value that represents the new filter position."""
