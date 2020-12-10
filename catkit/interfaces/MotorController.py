from abc import ABC, abstractmethod
import logging

"""Interface for a motor controller."""


class MotorController(ABC):
    log = logging.getLogger(__name__)

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with the DM and sets class attributes for 'config_id' and 'dm'."""
        self.config_id = config_id
        self.socket_id = None
        self._keep_alive = False
        self.instrument = None

        # Connect.
        self.motor_controller = self.initialize(*args, **kwargs)
        self.instrument = self.motor_controller
        self.log.info("Initialized Motor Controller " + config_id)

    # Implementing context manager.
    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        try:
            if not self._keep_alive:
                try:
                    if self.instrument:
                        self.close()
                finally:
                    self.motor_controller = None
                    self.instrument = None
                self.log.info("Safely closed connection to Motor Controller " + self.config_id)
        finally:
            # Reset, single use basis only.
            self._keep_alive = False

    # Abstract Methods.
    @abstractmethod
    def initialize(self, *args, **kwargs):
        """Creates an instance of the controller library and opens a connection."""

    @abstractmethod
    def close(self):
        """Close dm connection safely."""

    @abstractmethod
    def absolute_move(self, motor_id, position):
        """Implements an absolute move"""

    @abstractmethod
    def relative_move(self, motor_id, distance):
        """Implements an absolute move"""

    @abstractmethod
    def get_position(self, motor_id):
        """Returns the current position of a motor."""
