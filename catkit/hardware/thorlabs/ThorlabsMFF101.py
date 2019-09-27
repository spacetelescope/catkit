try:
    import ftd2xx
except Exception as error:  # Raises OSError if it can't open driver lib
    raise ImportError("Missing libftd2xx driver? Download from https://www.ftdichip.com/Drivers/D2XX.htm") from error
import ftd2xx.defines as constants
import time
import logging
from hicat.interfaces.FlipMotor import FlipMotor
from hicat.config import CONFIG_INI
from catkit.hardware import testbed_state

"""Implementation of the FlipMotor interface for the Thorlabs MFF101 Flip Mount."""


class ThorlabsMFF101(FlipMotor):
    log = logging.getLogger(__name__)

    def initialize(self, *args, **kwargs):
        """Creates an instance of the controller library and opens a connection."""

        serial = CONFIG_INI.get(self.config_id, "serial")
        self.serial = serial

        # noinspection PyArgumentList
        motor = ftd2xx.openEx(bytes(serial, 'utf-8'))
        motor.setBaudRate(115200)
        motor.setDataCharacteristics(constants.BITS_8, constants.STOP_BITS_1, constants.PARITY_NONE)
        time.sleep(.05)
        motor.purge()
        time.sleep(.05)
        motor.resetDevice()
        motor.setFlowControl(constants.FLOW_RTS_CTS, 0, 0)
        motor.setRts()
        return motor

    def close(self):
        """Close dm connection safely."""
        self.motor.close()

    def move_to_position1(self):
        """Implements a move to the "up" position."""
        self.log.info("Moving to 'up' position")
        up_command = b"\x6A\x04\x00\x01\x21\x01"
        self.motor.write(up_command)
        testbed_state.background = True
        time.sleep(1)

    def move_to_position2(self):
        """Implements a move to "down" position """
        self.log.info("Moving to 'down' position")
        down_command = b"\x6A\x04\x00\x02\x21\x01"
        self.motor.write(down_command)
        testbed_state.background = False
        time.sleep(1)

    def blink_led(self):
        self.log.info(".blink.")
        self.motor.write(b"\x23\x02\x00\x00\x21\x01")
