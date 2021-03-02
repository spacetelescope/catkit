from enum import Enum

import pyvisa

from catkit.interfaces.FilterWheel import FilterWheel
from catkit.catkit_types import ColorWheelFilter, NDWheelFilter
import catkit.util


class ThorlabsFW102C(FilterWheel):
    """Abstract base class for filter wheels."""

    instrument_lib = pyvisa

    class Commands(Enum):
        GET_POSITION = "pos?"
        SET_POSITION = "pos="

    def initialize(self, visa_id, filter_type):
        """ Initializes class instance, but doesn't -- and shouldn't -- open a connection to the hardware."""

        self.visa_id = visa_id
        self.current_position = None

        if not issubclass(filter_type, (ColorWheelFilter, NDWheelFilter)):
            raise TypeError(f"Expected filter_type to be of ({(ColorWheelFilter, NDWheelFilter)}) not '{filter_type}'")
        self.filter_type = filter_type

    def _open(self):
        """Open connection. Return an object connected to the instrument hardware.
        """
        self.current_position = None

        rm = self.instrument_lib.ResourceManager('@py')

        # Open connection.
        self.instrument = rm.open_resource(self.visa_id,
                                           baud_rate=115200,
                                           data_bits=8,
                                           write_termination='\r',
                                           read_termination='\r')

        # Query position.
        self.get_position()

        return self.instrument

    def _close(self):
        self.current_position = None
        self.instrument.close()

    def comm(self, command):
        try:
            assert isinstance(command, str)
            # Send command.
            _bytes_written = self.instrument.write(command)  # bytes_written := len(command) + 1 due to '\r'.
            if self.instrument.last_status is self.instrument_lib.constants.StatusCode.success:
                # First read the echo to clear the buffer.
                self.instrument.read()

                if self.Commands.SET_POSITION.value in command:
                    return
                elif command == self.Commands.GET_POSITION.value:
                    # Now read the filter position, and convert to an integer.
                    return int(self.instrument.read())
                else:
                    raise NotImplementedError
            else:
                raise Exception(f"Filter wheel '{self.config_id}' returned an unexpected response: '{self.instrument.last_status}'")
        except Exception:
            self.current_position = None
            raise

    @property
    def current_filter(self):
        return self.filter_type(self.current_position)

    def get_position(self):
        """ Queries the device and returns the current filter wheel position index (int). """
        self.current_position = self.comm(self.Commands.GET_POSITION.value)
        return self.current_position

    def get_filter(self):
        """ Queries the device and returns the current filter wheel position enum member (self.filter_type(position)). """
        self.get_position()
        return self.current_filter

    def set_position(self, position, force=False):

        # Allow multiple formats for `position` and normalize to `self.filter_type`.
        filter = position if isinstance(position, self.filter_type) else self.filter_type(position)

        # Convert to integer position.
        position = filter.position

        # Do nothing if already in desired position (unless ``force is True``).
        if not force and (position == self.current_position):
            self.log.info(f"Filter wheel already at {position}")
            return

        # Move.
        self.log.info(f"Configuring filter wheel to position: '{position}'...")
        self.comm(f"{self.Commands.SET_POSITION.value}{position}")
        self.current_position = position
        # Wait for wheel to move. Fairly arbitrary 3s delay...
        catkit.util.sleep(3)  # TODO: CATKIT-82 make the sleep a function of position change.

    def move(self, position, force=False):
        return self.set_position(position=position, force=force)
