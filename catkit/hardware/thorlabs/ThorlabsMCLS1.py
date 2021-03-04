from ctypes import cdll
import os
import re

from catkit.interfaces.LaserSource import LaserSource
import catkit.util

"""Interface for a laser source."""

# Load Thorlabs uart lib, e.g., uart_library_win64.dll.
UART_lib = cdll.LoadLibrary(os.environ.get('CATKIT_THORLABS_UART_LIB_PATH'))


class ThorlabsMCLS1(LaserSource):

    instrument_lib = UART_lib

    def initialize(self,
                   device_id,
                   channel,
                   nominal_current,
                   power_off_on_exit=False,
                   sleep_time=2):

        self.channel = channel #CONFIG_INI.getint(self.config_id, "channel")
        self.nominal_current = nominal_current#CONFIG_INI.getint(self.config_id, "nominal_current")
        self.sleep_time = sleep_time  # Number of seconds to sleep after turning on laser or changing current.
        self.port = None
        self.power_off_on_exit = power_off_on_exit
        self.device_id = device_id# if device_id else CONFIG_INI.get(config_id, "device_id")

    def _open(self):
        self.port = self.find_com_port()
        # Open connection (handle).
        instrument = self.instrument_lib.fnUART_LIBRARY_open(self.port.encode(), 115200, 3)
        if instrument < 0:
            raise IOError(f"{self.config_id} connection failure on port: '{self.port}'")
        self.instrument = instrument

        # Set the initial current to nominal_current and enable the laser.
        self.set_current(self.nominal_current, sleep=False)
        self.set_channel_enable(self.channel, 1)
        self.set_system_enable(1)

        return self.instrument

    def _close(self):
        """Close laser connection safely"""
        if self.power_off_on_exit:
            if self.instrument_lib.fnUART_LIBRARY_isOpen(self.port.encode()) == 1:
                self.set_channel_enable(self.channel, 0)

                self.log.info("Checking whether to power off laser...")
                # Check if the other channels are enabled before turning off system enable.
                turn_off_system_enable = True
                for i in range(1, 5):
                    if self.is_channel_enabled(i) == 1:
                        turn_off_system_enable = False

                if turn_off_system_enable:
                    self.set_system_enable(0)
                self.instrument_lib.fnUART_LIBRARY_close(self.instrument)
        else:
            self.log.info("Power off on exit is False; leaving laser ON.")

    def set_current(self, value, sleep=True):
        """Sets the current on a given channel."""

        if self.get_current() != value:
            self.log.info("Laser is changing amplitude...")
            self.set_active_channel(self.channel)
            current_command_string = f"current={value}\r".encode()
            self.instrument_lib.fnUART_LIBRARY_Set(self.instrument, current_command_string, 32)
            if sleep:
                catkit.util.sleep(self.sleep_time)

    def get_current(self):
        """Returns the value of the laser's current."""
        self.set_active_channel(self.channel)
        command = "current?\r".encode()
        response_buffer = ("0" * 255).encode()
        self.instrument_lib.fnUART_LIBRARY_Get(self.instrument, command, response_buffer)
        response_buffer = response_buffer.decode()
        # Use regex to find the float value in the response.
        return float(re.findall("\d+\.\d+", response_buffer)[0])

    def find_com_port(self):
        """Queries the dll for the list of all com devices."""
        if not self.device_id:
            raise ValueError(f"{self.config_id}: requires a device ID to find a com port to connect to.")

        response_buffer = ("0" * 255).encode()
        self.instrument_lib.fnUART_LIBRARY_list(response_buffer, 255)
        response_buffer = response_buffer.decode()
        split = response_buffer.split(",")
        for i, thing in enumerate(split):
            # The list has a format of "Port, Device, Port, Device". Once we find device named VCPO, minus 1 for port.
            if thing == self.device_id:
                return split[i - 1]

        raise IOError(f"{self.config_id}: no port found for '{self.device_id}'")

    def set_channel_enable(self, channel, value):
        """
        Set the laser's channel enable.
        :param channel: Integer value for channel (1 - 4)
        :param value: Integer value, 1 is enabled, and 0 is disabled.
        """
        self.set_active_channel(channel)
        enable_command_string = f"enable={value}\r".encode()
        self.log.info(f"Laser is enabling channel '{channel}'...")
        self.instrument_lib.fnUART_LIBRARY_Set(self.instrument, enable_command_string, 32)
        if value == 1:
            catkit.util.sleep(self.sleep_time)

    def set_system_enable(self, value):
        """
        Set the laser's system enable.
        :param value: Integer value, 1 is enabled, and 0 is disabled.
        """
        enable_command_string = f"system={value}\r".encode()
        self.instrument_lib.fnUART_LIBRARY_Set(self.instrument, enable_command_string, 32)
        if value == 1:
            catkit.util.sleep(self.sleep_time)

    def set_active_channel(self, channel):
        # Set Active Channel.
        active_command_string = f"channel={channel}\r".encode()
        self.instrument_lib.fnUART_LIBRARY_Set(self.instrument, active_command_string, 32)

    def is_channel_enabled(self, channel):
        self.set_active_channel(channel)
        command = "enable?\r".encode()
        response_buffer = ("0" * 255).encode()
        self.instrument_lib.fnUART_LIBRARY_Get(self.instrument, command, response_buffer)
        response_buffer = response_buffer.decode()
        return bool(int(re.findall("\d+", response_buffer)[0]))
