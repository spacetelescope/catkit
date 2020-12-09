"""
Interface for the nPoint LC400 Tip/Tilt closed loop controller.
Connects to the controller via usb using pvisa and FTDI drivers.
"""


import enum
import functools
import math
import os
import struct
import time

import pyvisa

from catkit.interfaces.ClosedLoopController import ClosedLoopController


class Parameters(enum.Enum):
    # The hex codes get summed with the channel to yield an address so for convenience leave these as ints.
    # param = (hex_Code, data_length, data_type_fmt)
    LOOP = (0x84, 1, 'I')
    P_GAIN = (0x720, 2, 'd')
    I_GAIN = (0x728, 2, 'd')
    D_GAIN = (0x730, 2, 'd')

    def __init__(self, hex_code, data_length, data_type_fmt):
        self.hex_code = hex_code
        self.data_length = data_length
        self.data_type_fmt = data_type_fmt

    @classmethod
    def _missing_(cls, value):
        for item in cls:
            if value == item.hex_code:
                return item


class Commands(enum.Enum):
    SET = b'\xa2'
    SECOND_MSG = b'\xa3'
    GET_SINGLE = b'\xa0'
    GET_ARRAY = b'\xa4'


class NPointLC400(ClosedLoopController):
    
    instrument_lib = pyvisa

    endpoint = b'\x55'
    # The channels get summed with the parameters to yield an address so for convenience leave these as ints.
    base_channel_address = 0x11830000
    channel_address_offset = 0x1000
    channels = (1, 2)
    endian = '<'  # Little endian.

    def initialize(self, com_id, timeout=5):
        """Initial function to set vendor and product id parameters.
        Parameters
        ----------
        com_id : str
            The serial port com.
        """

        self.instrument_lib = self.instrument_lib.ResourceManager("@py")

        # Device specifics
        self.com_id = com_id
        self.timeout = timeout

    @classmethod
    def build_address(cls, parameter, channel):
        """ Builds the address to send to the controller.
        Memory offsets are summed with a channel base address to set the parameter for a specific channel.
        Channels are separated by an offset of 0x1000.
        0x11831000 := Ch1 base address
        0x11832000 := Ch2 base address
        """

        if parameter not in Parameters:
            raise ValueError(f"Parameter must be one of {[param for param in Parameters]}.")

        if channel not in cls.channels:
            raise ValueError(f"Channel must be one of {cls.channels}")

        # + := int addition.
        address = cls.base_channel_address + channel*cls.channel_address_offset + parameter.hex_code

        return struct.pack(cls.endian + 'I', address)  # 'I' := unsigned int.

    def _close(self):
        # Reset everything to 0.
        for channel in self.channels:
            for parameter in Parameters:
                self.set(parameter, channel, 0)
        self.instrument.close()

    def _open(self):
        # Instantiate the device.
        self.instrument = self.instrument_lib.open_resource(self.com_id,
                                                            access_mode=pyvisa.constants.AccessModes.exclusive_lock,
                                                            open_timeout=self.timeout)
        self.log.info('npointLC400 instantiated and logging online.')
        return self.instrument

    def _read(self, byte_count):
        """ Read a response from controller. """
        start = time.time()
        resp = self.instrument.read_bytes(byte_count)
        self.log.debug(f'It took {start - time.time()}s to read response.')
        return resp

    def _send(self, message):
        """ Send the message(s) to the controller. """
        message = message if isinstance(message, (tuple, list)) else [message]
        for msg in message:
            self.instrument.write_raw(msg)

    def get(self, parameter, channel):
        """
        (addr and data are 32b (4B) each).
        Read Single Location
            Number of bytes written: 6
            Format: 0xA0 [addr] 0x55
            Number of bytes read: 10
            Return Value: 0xA4 [addr] [data] 0x55
        Read Array Command
            Number of bytes written: 10
            Format: 0xA4 [addr] [numReads] 0x55
            Number of bytes read: 6 + numReads*4
            Return Value: 0xA4 [addr] [data 1].....[data N] 0x55
        """
        # Construct message.
        address = self.build_address(parameter, channel)
        n_reads = parameter.data_length
        if n_reads == 1:
            message = b''.join([Commands.GET_SINGLE.value, address, self.endpoint])
        else:
            n_reads_message = struct.pack(self.endian + 'I', n_reads)
            message = b''.join([Commands.GET_ARRAY.value, address, n_reads_message, self.endpoint])

        # Send GET.
        self._send(message)

        # Read response.
        bytes_to_read = 1 + 4 + n_reads*4 + 1  # command + address + n_reads*data + endpoint.
        resp = self._read(bytes_to_read)

        # Parse response.
        resp_command, resp_parameter, resp_address, resp_channel, value = self.parse_message(resp)

        # Check to ensure that reads are in sync.
        if resp_command not in (Commands.GET_SINGLE, Commands.GET_ARRAY):
            raise RuntimeError(f"Reads and writes out of sync. Expected GET Command but got '{resp_command}")
        if resp_parameter is not parameter:
            raise RuntimeError(f"Reads and writes out of sync. Expected Parameter '{parameter}' but got '{resp_parameter}")
        if address != resp_address:
            raise RuntimeError(f"Reads and writes out of sync. Expected address '{address}' but got '{resp_address}")
        if resp_channel != channel:
            raise RuntimeError(f"Reads and writes out of sync. Expected channel '{channel}' but got '{resp_channel}")

        return value

    def set(self, parameter, channel, value):
        """
        (addr and data are 32b (4B) each).
        Write Single Location Command
            Number of bytes written: 10
            Format: 0xA2 [addr] [data] 0x55
            Return Value: none
        Write Next Command
            Number of bytes written: 6
            Format: 0xA3 [data] 0x55
            Return Value: none
        """
        if not isinstance(value, (int, float)):
            raise TypeError(f"Parameter values must be int or float not {type(value)}")

        address = self.build_address(parameter, channel)

        data_type_fmt = parameter.data_type_fmt
        if data_type_fmt == 'I':
            value = struct.pack(self.endian + data_type_fmt, 1 if value else 0)
            self._send(b''.join([Commands.SET.value, address, value, self.endpoint]))
        elif data_type_fmt == 'd':
            value = struct.pack(self.endian + data_type_fmt, float(value))
            # Send value in two halves.
            self._send([b''.join([Commands.SET.value, address, value[:4], self.endpoint]),
                        b''.join([Commands.SECOND_MSG.value, value[4:], self.endpoint])])
        else:
            raise NotImplementedError("Supports only 32b ints and 64b floats.")

    def set_and_check(self, parameter, channel, value):
        self.set(parameter, channel, value)
        set_value = self.get(parameter, channel)
        if value != set_value:
            raise ValueError(f'Command was NOT successful : {value} != {set_value}.')  # RT error?
        self.log.debug(f'Command successful: {value} == {set_value}.')
        
    def get_status(self, channel):
        """ Get the value of all parameter: loop, and p/i/d_gain for the specified channel. Returns a dict. """
        value_dict = {}
        for parameter in Parameters:
            value_dict[parameter] = self.get(parameter, channel)
        self.log.info(f"Status: {value_dict}")
        return value_dict 

    def set_closed_loop(self, active=True):
        """ Activate closed-loop control on all channels. """
        for channel in self.channels:
            self.set_and_check(Parameters.LOOP, channel, active)

    @classmethod
    def parse_message(cls, message):
        """ Parse message.

        (addr and data are 32b (4B) each).
        Read Single Location
            Number of bytes written: 6
            Format: 0xA0 [addr] 0x55
            Number of bytes read: 10
            Return Value: 0xA4 [addr] [data] 0x55
        Read Array Command
            Number of bytes written: 10
            Format: 0xA4 [addr] [numReads] 0x55
            Number of bytes read: 6 + numReads*4
            Return Value: 0xA4 [addr] [data 1].....[data N] 0x55
        Write Single Location Command
            Number of bytes written: 10
            Format: 0xA2 [addr] [data] 0x55
            Return Value: none
        Write Next Command
            Number of bytes written: 6
            Format: 0xA3 [data] 0x55
            Return Value: none

        Returns:
            Command, Parameter, address, channel, data
        """

        # Parse command
        try:
            command = Commands(message[:1])
        except ValueError as error:
            raise NotImplementedError('Non implemented command found in message.') from error

        parameter = None
        address = None
        channel = None
        if command in (Commands.GET_SINGLE, Commands.GET_ARRAY, Commands.SET):
            # Parse address
            address = message[1:5]

            # Parse channel
            int_address = struct.unpack(cls.endian + 'I', address)[0]
            channel = math.floor((int_address - cls.base_channel_address) / cls.channel_address_offset)
            if channel not in cls.channels:
                raise ValueError(f"Channel out of bounds. Received '{channel}' expected one of ({cls.channels})")

            # Parse parameter
            try:
                parameter = Parameters(int_address - cls.base_channel_address - cls.channel_address_offset * channel)
            except ValueError as error:
                raise NotImplementedError('Non implemented parameter found in message.') from error

        # Parse value.
        if command in (Commands.SET, Commands.SECOND_MSG):
            data = struct.unpack(cls.endian + 'I', message[-5:-1])[0]
        elif command is Commands.GET_SINGLE:
            # 0xA0 [addr] 0x55
            # 0xA0 [addr] [data] 0x55
            data = struct.unpack(cls.endian + parameter.data_type_fmt, message[5:-1])[0] if len(message) > 6 else None
        elif command is Commands.GET_ARRAY:
            # For GET, message could be either that sent or that received. E.g., one of the following:
            # 0xA4 [addr] [numReads] 0x55
            # 0xA4 [addr] [data 1].....[data N] 0x55
            data_block = message[5:-1]
            n_data = len(data_block)//4
            if n_data == 1:
                data_type_fmt = 'I'
            elif n_data == 2:
                data_type_fmt = 'd'
            else:
                raise NotImplementedError(f"Supports only 32b ints and 64b floats. Received {n_data * 32}b data block.")
            data = struct.unpack(cls.endian + data_type_fmt, data_block)[0]
        else:
            raise NotImplementedError('Non implemented command found in message.')

        return command, parameter, address, channel, data
