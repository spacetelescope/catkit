from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

from builtins import *
from ctypes import *
import os
import re

from ...interfaces.LaserSource import LaserSource
from ...config import CONFIG_INI

"""Interface for a laser source."""


class ThorlabsMLCS1(LaserSource):

    def __init__(self, config_id, *args, **kwargs):
        """
        Child constructor to add a few hardware specific class attributes. Still calls the super.
        """
        super(ThorlabsMLCS1, self).__init__()
        self.channel = None
        self.nominal_current = None
        self.handle = None

    def initialize(self, *args, **kwargs):
        self.channel = CONFIG_INI.getint(self.config_id, "channel")
        self.nominal_current = CONFIG_INI.getint(self.config_id, "current")
        path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib", "uart_library_win64.dll")
        self.laser = cdll.LoadLibrary(bytes(path, "utf-8"))
        self.handle = self.laser.fnUART_LIBRARY_open(b"COM3", 115200, 3)

        # Set the initial current to nominal_current and enable the laser.
        self.set_current(self.channel, self.nominal_current)
        self.set_channel_enable(self.channel, 1)
        self.set_system_enable(1)

        return self.laser

    def close(self):
        """Close laser connection safely"""
        if self.laser.fnUART_LIBRARY_isOpen(b"COM3") != 1:
            self.set_channel_enable(self.channel, 0)
            self.set_system_enable(0)
            self.laser.fnUART_LIBRARY_close(self.handle)
        self.handle = None

    def set_current(self, channel, value):
        """Sets the current on a given channel."""
        self.set_active_channel(channel)
        current_command_string = b"current={}\r".format(value)
        self.laser.fnUART_LIBRARY_Set(self.handle, current_command_string, 32)

    def get_current(self, channel):
        """Returns the value of the laser's current."""
        self.set_active_channel(channel)
        command = b"current?\r"
        buffer = b"0" * 255
        response = self.laser.fnUART_LIBRARY_Get(self.handle, command, buffer)

        # Use regex to find the float value in the response.
        return float(re.findall("\d+\.\d+", response))

    def find_com_port(self):
        """Queries the dll for the com port it is using."""
        buffer = b"0" * 255
        self.laser.uart_dll.fnUART_LIBRARY_list(buffer, 255)
        return buffer.split(",")[0]

    def set_channel_enable(self, channel, value):
        """
        Set the laser's channel enable.
        :param channel: Integer value for channel (1 - 4)
        :param value: Integer value, 1 is enabled, and 0 is disabled.
        """
        self.set_active_channel(channel)
        enable_command_string = b"enable={}\r".format(value)
        self.laser.fnUART_LIBRARY_Set(self.handle, enable_command_string, 32)

    def set_system_enable(self, value):
        """
        Set the laser's system enable.
        :param value: Integer value, 1 is enabled, and 0 is disabled.
        """
        enable_command_string = b"system={}\r".format(value)
        self.laser.fnUART_LIBRARY_Set(self.handle, enable_command_string, 32)

    def set_active_channel(self, channel):
        # Set Active Channel.
        active_command_string = b"channel={}\r".format(channel)
        self.laser.fnUART_LIBRARY_Set(self.handle, active_command_string, 32)
