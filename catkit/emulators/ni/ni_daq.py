import logging
from collections import namedtuple
from abc import ABC, abstractmethod

import numpy as np

from catkit.config import CONFIG_INI


class NiDaqEmulator(ABC):
    """ Emulates the NI-DAQ device """

    def __init__(self, config_id):
        self.config_id = config_id
        self.System = self.EmulatedSystem(self)

        self.device_name = CONFIG_INI.get(self.config_id, 'device_name')

        self.voltages = {}

    @staticmethod
    def parse_channels(channels_string):
        channels = channels_string.split(',')
        channels = [ch.strip() for ch in channels]

        return [ch if len(ch) > 0]

    class ChannelList:
        def __init__(self):
            self.channel_names = []

        def add_ai_voltage_chan(self, channel_name):
            self.channel_names.append(channel_name)

        def add_ao_voltage_chan(self, channel_name):
            self.channel_names.append(channel_name)

    def Task(self):
        # This is a function instead of a class to pass on a reference to the main emulator object.
        return self.EmulatedTask(self)

    class EmulatedTask:
        def __init__(self, ni_daq_emulator):
            self.ni_daq_emulator = ni_daq_emulator

            self.ai_channels = ChannelList()
            self.ao_channels = ChannelList()

        def __enter__(self):
            pass

        def __exit__(self):
            pass

        def read(self):
            self.ni_daq_emulator._read(self.ai_channels.channel_names)

        def write(self, values):
            self.ni_daq_emulator._write(self.ao_channels.channel_names, values)

    def _read(self, channels):
        res = []
        for channel in channels:
            if channel not in self.voltages:
                # Don't support persistance of voltages beyond device lifetime.
                # Voltages get implicitly reset to zero when the device is started.
                self.voltages[channel] = 0

            res.append(self.voltages[channel])

        return np.array(res)

    def _write(self, channels, values):
        for channel, value in zip(channels, values):
            self.voltages[channel] = value

        self.sim_update_voltage(self.device_name, channel, value)

    class EmulatedSystem:
        def __init__(self, device_name):
            self.devices = [self.Device(device_name)]

        def local(self):
            return self

        Device = namedtuple("Device", "name")

    @abstractmethod
    def sim_update_voltage(self, device_name, channel_name, voltage):
        """ Update the simulator with this new voltage. """
