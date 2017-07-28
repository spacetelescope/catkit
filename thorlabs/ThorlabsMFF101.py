from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import ftd2xx
import ftd2xx.defines as constants
import time
from ...interfaces.FlipMotor import FlipMotor
from ...config import CONFIG_INI
from ...hardware import testbed_state

"""Implementation of the FlipMotor interface for the Thorlabs MFF101 Flip Mount."""


class ThorlabsMFF101(FlipMotor):

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
        up_command = b"\x6A\x04\x00\x01\x21\x01"
        self.motor.write(up_command)
        testbed_state.background = True

    def move_to_position2(self):
        """Implements a move to "down" position """
        down_command = b"\x6A\x04\x00\x02\x21\x01"
        self.motor.write(down_command)
        testbed_state.background = False

    def blink_led(self):
        self.motor.write(b"\x23\x02\x00\x00\x21\x01")
