from abc import ABC, abstractmethod
import logging

"""Interface for a two state flip motor."""


class FlipMotor(ABC):
    log = logging.getLogger(__name__)

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with the motor controller and sets class attributes for 'config_id' and 'motor'."""
        self.config_id = config_id
        self.serial = None
        self._keep_alive = False
        self.instrument = None

        # Connect.
        self.motor = self.initialize(*args, **kwargs)
        self.instrument = self.motor
        self.log.info("Opened connection to flip motor " + config_id)

    # Implementing context manager.
    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        try:
            if not self._keep_alive:
                try:
                    self.close()
                finally:
                    self.motor = None
                    self.instrument = None
                self.log.info(f"Safely closed connection to flip motor {self.config_id}")
        finally:
            # Reset, single use basis only.
            self._keep_alive = False

    # Abstract Methods.
    @abstractmethod
    def initialize(self, *args, **kwargs):
        """Creates an instance of the controller library and opens a connection."""

    @abstractmethod
    def close(self):
        """Close motor controller connection safely."""

    @abstractmethod
    def move_to_position(self, position_number):
        """ Calls move_to_position<position_number>. """

    @abstractmethod
    def move_to_position1(self):
        """Implements a move to position 1."""

    @abstractmethod
    def move_to_position2(self):
        """Implements a move to position 2."""
