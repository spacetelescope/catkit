from enum import Enum

try:
    import ftd2xx
except Exception as error:  # Raises OSError if it can't open driver lib
    raise ImportError("Missing libftd2xx driver? Download from https://www.ftdichip.com/Drivers/D2XX.htm") from error

from catkit.catkit_types import FlipMountPosition
from catkit.interfaces.FlipMotor import FlipMotor
import catkit.util

"""Implementation of the FlipMotor interface for the Thorlabs MFF101 Flip Mount."""


class ThorlabsMFF101(FlipMotor):

    instrument_lib = ftd2xx

    class Command(Enum):
        MOVE_TO_POSITION_1 = b"\x6A\x04\x00\x01\x21\x01"
        MOVE_TO_POSITION_2 = b"\x6A\x04\x00\x02\x21\x01"
        BLINK_LED = b"\x23\x02\x00\x00\x21\x01"

    def initialize(self, serial, in_beam_position):
        """Creates an instance of the controller library and opens a connection."""

        self.serial = serial
        self.in_beam_position = in_beam_position
        self.out_of_beam_position = 1 if in_beam_position == 2 else 2

    def _open(self):
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

    def move_to_position(self, position):
        """ Calls move_to_position<position_number>(). """

        if isinstance(position, FlipMountPosition):
            position = self.in_beam_position if position is FlipMountPosition.IN_BEAM else self.out_of_beam_position

        # return self.__getattribute__(f"move_to_position{position_number}")
        if position == 1:
            return self.move_to_position1()
        elif position == 2:
            return self.move_to_position2()
        else:
            raise NotImplementedError

    def move_to_position1(self):
        """ Implements a move to the "up" position. """
        is_in_beam = self.in_beam_position == 1
        self.log.info(f"Moving to 'up' position (1), which is {'in' if is_in_beam else 'out of'} beam")
        self.instrument.write(self.Command.MOVE_TO_POSITION_1)
        catkit.util.sleep(1)

    def move_to_position2(self):
        """ Implements a move to "down" position. """
        is_in_beam = self.in_beam_position == 2
        inout_label = 'in' if is_in_beam else "out of"
        self.log.info(f"Moving to 'up' position (2), which is {'in' if is_in_beam else 'out of'} beam")
        self.instrument.write(self.Command.MOVE_TO_POSITION_2)
        catkit.util.sleep(1)

    def blink_led(self):
        self.log.info(".blink.")
        self.instrument.write(self.Command.BLINK_LED)
