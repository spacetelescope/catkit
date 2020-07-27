try:
    import ftd2xx
except Exception as error:  # Raises OSError if it can't open driver lib
    raise ImportError("Missing libftd2xx driver? Download from https://www.ftdichip.com/Drivers/D2XX.htm") from error
import ftd2xx.defines as constants
import time
import logging
from catkit.interfaces.FlipMotor import FlipMotor
from catkit.config import CONFIG_INI

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

    def move_to_position(self, position_number):
        """ Calls move_to_position<position_number>. """
        #return self.__getattribute__(f"move_to_position{position_number}")
        if position_number == 1:
            return self.move_to_position1()
        elif position_number == 2:
            return self.move_to_position2()
        else:
            raise NotImplementedError

    def move_to_position1(self):
        """Implements a move to the "up" position."""
        is_in_beam = CONFIG_INI.getint(self.config_id, 'in_beam_position') == 1
        inout_label = 'in' if is_in_beam else "out of"
        self.log.info(f"Moving to 'up' position, which is {inout_label} beam")
        up_command = b"\x6A\x04\x00\x01\x21\x01"
        self.motor.write(up_command)
        time.sleep(1)

    def move_to_position2(self):
        """Implements a move to "down" position """
        is_in_beam = CONFIG_INI.getint(self.config_id, 'in_beam_position') == 2
        inout_label = 'in' if is_in_beam else "out of"
        self.log.info(f"Moving to 'down' position, which is {inout_label} beam")
        down_command = b"\x6A\x04\x00\x02\x21\x01"
        self.motor.write(down_command)
        time.sleep(1)

    def blink_led(self):
        self.log.info(".blink.")
        self.motor.write(b"\x23\x02\x00\x00\x21\x01")
