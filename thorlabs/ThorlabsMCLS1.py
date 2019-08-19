from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
from ctypes import cdll
import logging
import os
import re
import time

from ...interfaces.LaserSource import LaserSource
from ...config import CONFIG_INI
from ...hardware import testbed_state

"""Interface for a laser source."""


class ThorlabsMCLS1(LaserSource):
    SLEEP_TIME = 2  # Number of seconds to sleep after turning on laser or changing current.
    log = logging.getLogger(__name__)

    def __init__(self, config_id, *args, **kwargs):
        """
        Child constructor to add a few hardware specific class attributes. Still calls the super.
        """
        self.channel = None
        self.nominal_current = None
        self.handle = None
        self.port = None
        super(ThorlabsMCLS1, self).__init__(config_id, *args, **kwargs)

    def initialize(self, *args, **kwargs):
        """Starts laser at the nominal_current value from config.ini."""
        self.channel = CONFIG_INI.getint(self.config_id, "channel")
        self.nominal_current = CONFIG_INI.getint(self.config_id, "nominal_current")
        path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib", "uart_library_win64.dll")

        # noinspection PyArgumentList
        self.laser = cdll.LoadLibrary(path)
        self.port = self.find_com_port()
        self.handle = self.laser.fnUART_LIBRARY_open(self.port.encode(), 115200, 3)

        # Set the initial current to nominal_current and enable the laser.
        self.set_current(self.nominal_current, sleep=False)
        self.set_channel_enable(self.channel, 1)
        self.set_system_enable(1)

        return self.laser

    def close(self):
        """Close laser connection safely"""
        if self.laser.fnUART_LIBRARY_isOpen(self.port.encode()) == 1:
            self.set_channel_enable(self.channel, 0)

            # Check if the other channels are enabled before turning off system enable.
            turn_off_system_enable = True
            for i in range(1, 5):
                if self.is_channel_enabled(i) == 1:
                    turn_off_system_enable = False

            if turn_off_system_enable:
                self.set_system_enable(0)
            self.laser.fnUART_LIBRARY_close(self.handle)
        self.handle = None

        # Update testbed_state.
        testbed_state.laser_source = None
        testbed_state.laser_value = None

    def set_current(self, value, sleep=True):
        """Sets the current on a given channel."""

        if self.get_current() != value:
            self.log.info("Laser is changing amplitude...")
            self.set_active_channel(self.channel)
            current_command_string = "current={}\r".format(value).encode()
            self.laser.fnUART_LIBRARY_Set(self.handle, current_command_string, 32)
            if sleep:
                time.sleep(self.SLEEP_TIME)

        # Update the testbed_state.
        testbed_state.laser_source = self.config_id
        testbed_state.laser_value = value

    def get_current(self):
        """Returns the value of the laser's current."""
        self.set_active_channel(self.channel)
        command = "current?\r".encode()
        response_buffer = ("0" * 255).encode()
        self.laser.fnUART_LIBRARY_Get(self.handle, command, response_buffer)
        response_buffer = response_buffer.decode()
        # Use regex to find the float value in the response.
        return float(re.findall("\d+\.\d+", response_buffer)[0])

    def find_com_port(self):
        """Queries the dll for the com port it is using."""
        response_buffer = ("0" * 255).encode()
        self.laser.fnUART_LIBRARY_list(response_buffer, 255)
        response_buffer = response_buffer.decode()
        split = response_buffer.split(",")
        for i, thing in enumerate(split):

            # The list has a format of "Port, Device, Port, Device". Once we find device named VCPO, minus 1 for port.
            if thing == "\\Device\\VCP0":
                return split[i - 1]

        # Return None keyword if not found.
        return None

    def set_channel_enable(self, channel, value):
        """
        Set the laser's channel enable.
        :param channel: Integer value for channel (1 - 4)
        :param value: Integer value, 1 is enabled, and 0 is disabled.
        """
        self.set_active_channel(channel)
        enable_command_string = "enable={}\r".format(value).encode()
        self.laser.fnUART_LIBRARY_Set(self.handle, enable_command_string, 32)
        if value == 1:
            self.log.info("Laser is enabling channel " + str(channel) + "...")
            time.sleep(self.SLEEP_TIME)

    def set_system_enable(self, value):
        """
        Set the laser's system enable.
        :param value: Integer value, 1 is enabled, and 0 is disabled.
        """
        enable_command_string = "system={}\r".format(value).encode()
        self.laser.fnUART_LIBRARY_Set(self.handle, enable_command_string, 32)
        if value == 1:
            time.sleep(self.SLEEP_TIME)

    def set_active_channel(self, channel):
        # Set Active Channel.
        active_command_string = "channel={}\r".format(channel).encode()
        self.laser.fnUART_LIBRARY_Set(self.handle, active_command_string, 32)

    def is_channel_enabled(self, channel):
        self.set_active_channel(channel)
        command = "enable?\r".encode()
        response_buffer = ("0" * 255).encode()
        self.laser.fnUART_LIBRARY_Get(self.handle, command, response_buffer)
        response_buffer = response_buffer.decode()
        result = int(re.findall("\d+", response_buffer)[0])
        return result
