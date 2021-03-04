from ctypes import cdll
from enum import Enum
import os
import re

from catkit.interfaces.LaserSource import LaserSource
import catkit.util

"""Interface for a laser source."""

# Load Thorlabs uart lib, e.g., uart_library_win64.dll.
UART_lib = cdll.LoadLibrary(os.environ.get('CATKIT_THORLABS_UART_LIB_PATH'))


class ThorlabsMCLS1(LaserSource):

    instrument_lib = UART_lib

    class Command(Enum):
        TERM_CHAR = "\r"
        GET_CURRENT = "current?"
        SET_CURRENT = "current="
        GET_ENABLE = "enable?"
        SET_ENABLE = "enable="
        SET_SYSTEM = "system="
        SET_CHANNEL = "channel="

        # The following are untested.
        GET_COMMANDS = "?"
        GET_ID = "id?"
        GET_CHANNEL = "channel?"
        GET_TARGET_TEMP = "target?"
        SET_TARGET_TEMP = "target="
        GET_TEMP = "temp?"
        GET_POWER = "power?"
        GET_SYSTEM = "system?"
        GET_SPECS = "specs?"
        GET_STEP = "step?"
        SET_STEP = "step="
        SAVE = "save"
        GET_STATUS = "statword"

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
        self.set_channel_enable(self.channel, True)
        self.set_system_enable(True)

        return self.instrument

    def _close(self):
        """Close laser connection safely"""
        if self.power_off_on_exit:
            if self.instrument_lib.fnUART_LIBRARY_isOpen(self.port.encode()) == 1:
                self.set_channel_enable(self.channel, False)

                self.log.info("Checking whether other channels enable before powering off laser...")
                # Check if the other channels are enabled before turning off system enable.
                turn_off_system_enable = True
                for i in range(1, 5):
                    if self.is_channel_enabled(i):
                        turn_off_system_enable = False
                        if i == self.channel:
                            raise RuntimeError(f"Failed to disable channel: '{self.channel}")
                        break

                if turn_off_system_enable:
                    self.log.info("Powering off laser (system wide).")
                    self.set_system_enable(False)
                else:
                    self.log.info("Other channels enabled, NOT powering off laser (system wide).")
                self.instrument_lib.fnUART_LIBRARY_close(self.instrument)
        else:
            self.log.info("Power off on exit is False; leaving laser ON.")

    def get(self, command, channel=None):
        self.set_active_channel(channel=channel)
        command = command + self.Command.TERM_CHAR
        response_buffer = ("0" * 255)
        self.instrument_lib.fnUART_LIBRARY_Get(self.instrument, command.encode(), response_buffer.encode())
        return response_buffer.decode()

    def set(self, command, value, channel=None):
        if isinstance(value, bool):
            value = int(value)

        if command not in (self.Command.SET_CHANNEL, self.Command.SET_SYSTEM):
            self.set_active_channel(channel=channel)

        # WARNING! The device may have multiple connections and thus a race exits between setting the channel and
        # then commanding that channel. See HICAT-542.

        command = f"{command}{value}{self.Command.TERM_CHAR}"
        self.instrument_lib.fnUART_LIBRARY_Set(self.instrument, command.encode(), 32)

    def set_current(self, value, channel=None, sleep=True):
        """Sets the current on a given channel."""
        if self.get_current(channel=channel) != value:
            self.log.info("Laser is changing amplitude...")
            self.set(self.Command.SET_CURRENT, value, channel=channel)
            if sleep:
                catkit.util.sleep(self.sleep_time)

    def get_current(self, channel=None):
        """ Returns the value of the laser's current. """
        return float(re.findall("\d+\.\d+", self.get(self.Command.GET_CURRENT, channel=channel))[0])

    @property
    def current(self):
        # The laser can handle multiple connections and thus we can't mutex and store state locally so must query the device.
        return self.get_current(channel=self.channel)

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
        """ Set the laser's channel enable.
        :param channel: Integer value for channel (1 - 4)
        :param value: Integer, bool value, 1 is enabled, and 0 is disabled.
        """
        self.log.info(f"Laser is enabling channel '{channel}'...")
        self.set(self.Command.SET_ENABLE, value, channel=channel)
        if value:
            catkit.util.sleep(self.sleep_time)

    def set_system_enable(self, value):
        """ Set the laser's system enable. """
        self.set(self.Command.SET_SYSTEM, value)
        if value:
            catkit.util.sleep(self.sleep_time)

    def set_active_channel(self, channel=None):
        channel = channel if channel else self.channel
        self.set(self.Command.SET_CHANNEL, value=channel)

    def is_channel_enabled(self, channel=None):
        return bool(int(re.findall("\d+", self.get(self.Command.GET_ENABLE, channel=channel))[0]))
