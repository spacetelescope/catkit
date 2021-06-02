import importlib
import logging

from catkit.interfaces.DataAcquisitionDevice import DataAcquisitionDevice
from catkit.config import CONFIG_INI


class LazyLoadLibraryMeta(type):
    # Forward any call to a function to the library. Autoload the library upon first call.
    def __getattr__(cls, name):
        lib = cls.load_library()

        return getattr(lib, name)


class NiDaqLibrary(metaclass=LazyLoadLibraryMeta):
    _library = None

    # The class is not an abstract method.
    __isabstractmethod__ = False

    @classmethod
    def load_library(cls):
        if cls._library is not None:
            return cls._library

        cls._library = importlib.import_module('nidaqmx')

        return cls._library


class NiDaq(DataAcquisitionDevice):
    instrument_lib = NiDaqLibrary

    def initialize(self):
        self.log = logging.getLogger(__name__)

    def _open(self):
        '''Opens the device.

        This makes sure the device is connected the computer.

        Returns
        -------
        True
        '''
        # Read device name and desired channels from config file.
        self.device_name = CONFIG_INI.get(self.config_id, 'device_name')

        self.input_channels = self.parse_channels(CONFIG_INI.get(self.config_id, 'input_channels'))
        self.output_channels = self.parse_channels(CONFIG_INI.get(self.config_id, 'output_channels'))

        # Make sure this device name is connected.
        system = self.instrument_lib.System.local()
        for device in system.devices:
            if self.device_name == device.name:
                break
        else:
            raise ValueError(f'Device {self.device_name} is not connected.')

        return True

    @staticmethod
    def parse_channels(channels_string):
        '''Parse a string containing a comma-separated list of channel names.

        Parameters
        ----------
        channels_string : string
            A comma-separated list of channel names.

        Returns
        -------
        list of strings
            A list of all channel names.
        '''
        channels = channels_string.split(',')
        channels = [ch.strip() for ch in channels]

        return [ch if len(ch) > 0]

    def _close(self):
        pass

    def read_multichannel(self):
        '''Read voltages from all configured input channels.

        Returns
        -------
        ndarray
            The voltages for each of the channels.
        '''
        with self.instrument_lib.Task() as task:
            for channel in self.input_channels:
                channel_name = self.device_name + '/' + channel
                task.ai_channels.add_ao_voltage_chan(channel_name)

    def read_singlechannel(self, channel):
        '''Read voltages for a specific named channel.

        Parameters
        ----------
        channel : string
            The string identifier for the channel, eg. "ai0".

        Returns
        -------
        scalar
            The measured voltage for this channel.
        '''
        with self.instrument_lib.Task() as task:
            channel_name = self.device_name + '/' + channel
            task.ai_channels.add_ao_voltage_chan(channel_name)

            return task.read()

    def write_multichannel(self, values):
        '''Write voltages to all configured output channels.

        Parameters
        ----------
        values : ndarray
            An array containing the voltages for each channel.

        Raises
        ------
        ValueError
            In case the number of elements in `values` is not correct.
        '''
        if len(values) != len(self.channels):
            raise ValueError(f'The values should have the same length as the number of output channels ({len(self.output_channels)}) .')

        with self.instrument_lib.Task() as task:
            for channel in self.output_channels:
                channel_name = self.device_name + '/' + channel
                task.ao_channels.add_ao_voltage_chan(channel_name)

            task.write(values)

    def write_singlechannel(self, value, channel):
        '''Write a voltage to a specific named channel.

        Parameters
        ----------
        value : scalar
            The voltage to write to the channel.
        channel : string
            The string identifier for the channel, eg. "ao0".
        '''
        with self.instrument_lib.Task() as task:
            channel_name = self.device_name + '/' + channel
            task.ao_channels.add_ao_voltage_chan(channel_name)

            task.write(value)
