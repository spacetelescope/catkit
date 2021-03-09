from ctypes import cdll
from enum import Enum
import os
import re

from catkit.interfaces.LaserSource import LaserSource
import catkit.util

"""Interface for a laser source."""

# Load Thorlabs uart lib, e.g., uart_library_win64.dll.
try:
    UART_lib = cdll.LoadLibrary(os.environ.get('CATKIT_THORLABS_UART_LIB_PATH'))
except Exception as error:
    UART_lib = error


class ThorlabsMCLS1(LaserSource):

    instrument_lib = UART_lib

    class Command(Enum):
        TERM_CHAR = "\r"
        GET_CURRENT = "current?"
        SET_CURRENT = "current="
        GET_ENABLE = "enable?"
        SET_ENABLE = "enable="
        SET_SYSTEM = "system="
        GET_CHANNEL = "channel?"
        SET_CHANNEL = "channel="

        # The following are untested.
        GET_COMMANDS = "?"
        GET_ID = "id?"
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

    def __init__(self, *args, **kwargs):
        if isinstance(self.instrument_lib, BaseException):
            raise self.instrument_lib
        super().__init__(*args, **kwargs)

    def initialize(self,
                   device_id,
                   channel,
                   nominal_current,
                   power_off_on_exit=False,
                   sleep_time=2):

        self.channel = channel
        self.nominal_current = nominal_current
        self.sleep_time = sleep_time  # Number of seconds to sleep after turning on laser or changing current.
        self.port = None
        self.power_off_on_exit = power_off_on_exit
        self.device_id = device_id
        self.instrument_handle = None

    def _open(self):
        self.port = self.find_com_port()
        # Open connection (handle).
        self.instrument_handle = self.instrument_lib.fnUART_LIBRARY_open(self.port.encode(), 115200, 3)
        if self.instrument_handle < 0:
            raise IOError(f"{self.config_id} connection failure on port: '{self.port}'")
        self.instrument = True  # instrument_handle can be 0 which will result in _close() not being called.

        # Set the initial current to nominal_current and enable the laser.
        self.set_current(self.nominal_current, sleep=False)
        self.set_channel_enable(self.channel, True)
        self.set_system_enable(True)

        return self.instrument

    def _close(self):
        """Close laser connection safely"""
        try:
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
            else:
                self.log.info("Power off on exit is False; leaving laser ON.")
        finally:
            try:
                self.instrument_lib.fnUART_LIBRARY_close(self.instrument_handle)
            finally:
                self.instrument_handle = None

    def get(self, command, channel=None):
        if command not in (self.Command.GET_CHANNEL,):
            self.set_active_channel(channel=channel)

        command = command.value + self.Command.TERM_CHAR.value
        response_buffer = bytearray(255)
        self.instrument_lib.fnUART_LIBRARY_Get(self.instrument_handle, command.encode(), response_buffer)
        return response_buffer.rstrip(b"\x00").decode()

    def set(self, command, value, channel=None):
        if isinstance(value, bool):
            value = int(value)

        if command not in (self.Command.SET_CHANNEL, self.Command.SET_SYSTEM):
            self.set_active_channel(channel=channel)

        # WARNING! The device may have multiple connections and thus a race exits between setting the channel and
        # then commanding that channel. See HICAT-542.

        command = f"{command.value}{value}{self.Command.TERM_CHAR.value}"
        self.instrument_lib.fnUART_LIBRARY_Set(self.instrument_handle, command.encode(), 32)

    def get_int(self, command, channel=None):
        return float(re.findall("[0-9]+", self.get(command, channel=channel))[0])

    def get_bool(self, command, channel=None):
        return bool(self.get_int(command, channel=channel))

    def get_float(self, command, channel=None):
        return float(re.findall("[0-9]+.[0-9]+", self.get(command, channel=channel))[0])

    def set_current(self, value, channel=None, sleep=True):
        """Sets the current on a given channel."""
        if self.get_current(channel=channel) != value:
            self.log.info("Laser is changing amplitude...")
            self.set(self.Command.SET_CURRENT, value, channel=channel)
            if sleep:
                catkit.util.sleep(self.sleep_time)

    def get_current(self, channel=None):
        """ Returns the value of the laser's current. """
        return self.get_float(self.Command.GET_CURRENT, channel=channel)

    @property
    def current(self):
        # The laser can handle multiple connections and thus we can't mutex and store state locally so must query the device.
        return self.get_current(channel=self.channel)

    def find_com_port(self):
        """Queries the dll for the list of all com devices."""
        if not self.device_id:
            raise ValueError(f"{self.config_id}: requires a device ID to find a com port to connect to.")

        response_buffer = bytearray(255)
        self.instrument_lib.fnUART_LIBRARY_list(response_buffer, 255)
        response_buffer = response_buffer.decode()
        split = response_buffer.split(",")
        for i, thing in enumerate(split):
            # The list has a format of "Port, Device, Port, Device". Once we find device named VCPO, minus 1 for port.
            if self.device_id in thing:
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

    def get_active_channel(self):
        return self.get_int(self.Command.GET_CHANNEL)

    def is_channel_enabled(self, channel=None):
        return self.get_bool(self.Command.GET_ENABLE, channel=channel)
