from enum import Enum

try:
    import ftd2xx
except OSError as error:  # Raises OSError if it can't open driver lib
    ftd2xx = error

from catkit.catkit_types import FlipMountPosition
from catkit.interfaces.FlipMotor import FlipMotor
import catkit.util

"""Implementation of the FlipMotor interface for the Thorlabs MFF101 Flip Mount."""


class ThorlabsMFF101(FlipMotor):

    instrument_lib = ftd2xx

    def __init__(self, *arg, **kwargs):
        if isinstance(self.instrument_lib, BaseException):
            error = self.instrument_lib
            raise ImportError("Missing libftd2xx driver? Download from https://www.ftdichip.com/Drivers/D2XX.htm") from error
        super().__init__(*arg, **kwargs)

    class Command(Enum):
        MOVE_TO_POSITION_1 = b"\x6A\x04\x00\x01\x21\x01"
        MOVE_TO_POSITION_2 = b"\x6A\x04\x00\x02\x21\x01"
        BLINK_LED = b"\x23\x02\x00\x00\x21\x01"

    def initialize(self, serial, in_beam_position):
        """Creates an instance of the controller library and opens a connection."""

        self.serial = serial
        self.in_beam_position = in_beam_position
        self.out_of_beam_position = 1 if in_beam_position == 2 else 2
        self.current_position = None

    def _open(self):
        self.current_position = None
        # Open.
        self.instrument = self.instrument_lib.openEx(self.serial.encode())

        # Configure.
        self.instrument.setBaudRate(115200)
        self.instrument.setDataCharacteristics(self.instrument_lib.defines.BITS_8,
                                               self.instrument_lib.defines.STOP_BITS_1,
                                               self.instrument_lib.defines.PARITY_NONE)
        catkit.util.sleep(.05)
        self.instrument.purge()
        catkit.util.sleep(.05)
        self.instrument.resetDevice()
        self.instrument.setFlowControl(self.instrument_lib.defines.FLOW_RTS_CTS, 0, 0)
        self.instrument.setRts()

        return self.instrument

    def _close(self):
        """Close dm connection safely."""
        self.instrument.close()
        self.current_position = None

    def move_to_position(self, position, force=False):
        if isinstance(position, FlipMountPosition):
            beam_position = position
            position = self.in_beam_position if position is FlipMountPosition.IN_BEAM else self.out_of_beam_position
        else:
            assert position in (1, 2)
            beam_position = FlipMountPosition.IN_BEAM if position == self.in_beam_position else FlipMountPosition.OUT_OF_BEAM

        if not force and beam_position is not None and beam_position is self.current_position:
            # Already in desired position.
            self.log.info(f"Not moving '{self.config_id}' as it's already '{beam_position}' (position='{position}').")
            return

        if position == 1:
            command = self.Command.MOVE_TO_POSITION_1
        elif position == 2:
            command = self.Command.MOVE_TO_POSITION_2
        else:
            raise NotImplementedError

        self.log.info(f"Moving to '{beam_position}' (position='{position}')...")
        self.instrument.write(command.value)
        catkit.util.sleep(1)
        self.current_position = beam_position

    def move(self, position, force=False):
        return self.move_to_position(position=position, force=force)

    def move_to_position1(self):
        """ Implements a move to the "up" position. """
        self.move_to_position(1)

    def move_to_position2(self):
        """ Implements a move to "down" position. """
        self.move_to_position(2)

    def blink_led(self):
        self.log.info(".blink.")
        self.instrument.write(self.Command.BLINK_LED.value)
