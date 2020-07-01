"""
Interface for the nPoint Tip/Tilt closed loop controller. 
Connects to the controller via usb, and then sends and receives
messages to send commands, check the status, and put error handling over
top. 

In order to connect to the physical box, you'll need libusb appropriately
installed and have the driver for you machine set : Ex 
CATKIT_LIBUSB_PATH = 'C:\\Users\\HICAT\\Desktop\\libusb-win32-bin-1.2.6.0\\bin\\amd64\\libusb0.dll'
"""


import enum
import functools
import math
import os
import struct
import time

from usb.backend import libusb0, libusb1
import usb.core
import usb.util

from catkit.interfaces.ClosedLoopController import ClosedLoopController


class Parameters(enum.Enum):
    # These get summed with the channel to yield an address so for convenience leave these as ints.
    LOOP = 0x84
    P_GAIN = 0x720
    I_GAIN = 0x728
    D_GAIN = 0x730


class Commands(enum.Enum):
    SET = b'0xA2'
    SECOND_MSG = b'0xA3'
    GET = b'0xA4'


# Decorator with error handling
def usb_except(function):
    """Decorator that catches PyUSB errors."""

    @functools.wraps(function)
    def wrapper(self, *args, **kwargs):
        try:
            return function(self, *args, **kwargs)
        except usb.core.USBError as error:
            raise Exception('USB connection error.') from error

    return wrapper


class NPointTipTiltController(ClosedLoopController):
    """NPointTipTiltController connection class.

    This nPointTipTilt class acts as a useful connection and storage vehicle 
    for commands sent to the nPoint FTID LC400 controller. It has built in 
    functions that allow for writing commands, checking the status, etc. 
    By instantiating the nPointTipTilt object you find the LC400 controller 
    and set the default configuration. Memory managers in the back end 
    should close the connection when the time is right.
    """
    
    instrument_lib = usb.core

    library_mapping = {'libusb0': libusb0, 'libusb1': libusb1}
    # TODO: THe following usb_<x>_endpoint, I think, can be, and therefore should be, retrieved from self.get_config().
    usb_read_endpoint = b'0x81'
    usb_send_endpoint = b'0x02'
    endpoint = b'0x55'
    # The channels get summed with the parameters to yield an address so for convenience leave these as ints.
    base_channel_address = 0x11830000
    channel_address_offset = 0x1000
    channels = (1, 2)
    endian = '<'  # Little endian.
    message_length = 100

    def initialize(self, vendor_id, product_id, library_path=None, library='libusb0', timeout=60):
        """Initial function to set vendor and product id parameters.
        Parameters
        ----------
        vendor_id : int
            The vendor ID for the device, defaults to None.
        product_id : int 
            The produce ID for the device, defautls to None.
        library_path : str
            The path to the libusb library. Defaults to None.
        library : str
            Which libusb library, right now supports libusb0 and libusb1. Defaults to None.
        """
        
        # Device specifics
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.dev = None
        self.timeout = timeout

        self.library_path = os.environ.get('CATKIT_LIBUSB_PATH') if library_path is None else library_path
        if not self.library_path:
            raise OSError("No library path was passed to the npoint and CATKIT_LIBUSB_PATH is not set on your machine")

        if library not in self.library_mapping:
            raise NotImplementedError(f"The backend you specified ({library}) is not available at this time.")
        elif not os.path.exists(self.library_path):
            raise FileNotFoundError(f"The library path you specified ({self.library_path}) does not exist.")
        else:
            self.library = self.library_mapping[library]
            self.backend = self.library.get_backend(find_library=lambda x: self.library_path)

    @classmethod
    def build_address(cls, parameter, channel):
        """ Builds the message to send to the controller.
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
        address = cls.base_channel_address + channel*cls.channel_address_offset + parameter.value

        return struct.pack(cls.endian + 'I', address)  # 'I' := unsigned int.

    def _close(self):
        # Reset everything to 0.
        for channel in self.channels:
            for parameter in Parameters:
                self.set(parameter, channel, 0)

    def _open(self):
        # Instantiate the device.
        self.instrument = self.instrument_lib.find(idVendor=self.vendor_id, idProduct=self.product_id, backend=self.backend)
        if self.instrument is None:
            raise NameError(f"Go get the device sorted you knucklehead.\nVendor id {self.vendor_id} and product id {self.product_id} could not be found and connected.")
             
        # Set to default configuration -- for LC400 this is the right one.
        self.dev = self.instrument  # For legacy purposes
        self.instrument.set_configuration()
        self.log.info('nPointTipTilt instantiated and logging online.')
        
        return self.instrument

    def _read(self):
        """ Read a response from controller. """
        resp = ''
        start = time.time()
        resp = self.instrument.read(self.usb_read_endpoint, self.message_length, self.timeout)
        self.log.debug(f'It took {start - time.time()}s to read response.')

        if len(resp) < 4:
            raise RuntimeError("No response from controller.")

        return resp

    def _send(self, message):
        """ Send the message(s) to the controller. """
        message = message if isinstance(message, (tuple, list)) else [message]
        for msg in message:
            self.instrument.write(self.usb_send_endpoint, msg, self.timeout)

    @usb_except
    def get(self, parameter, channel):
        """
        Read Array Command
            Number of bytes: 10
            Format: 0xA4 [addr] [numReads] 0x55
            Return Value: 0xA4 [addr] [data 1].....[data N] 0x55
        """
        # Construct message.
        n_reads = 1 if parameter is Parameters.LOOP else 2
        n_reads = struct.pack(NPointTipTiltController.endian + 'I', n_reads)
        address = self.build_address(parameter, channel)
        message = b''.join([Commands.GET.value, address, n_reads, self.endpoint])

        # Send GET.
        self._send(message)

        # Read response.
        resp = self._read()

        # Parse response.
        resp_command, resp_parameter, resp_address, resp_channel, value = self.parse_message(resp)

        # Check to ensure that reads are in sync.
        if resp_command is not Commands.GET:
            raise RuntimeError(f"Reads and writes out of sync. Expected Command '{Commands.GET}' but got '{resp_command}")
        if resp_parameter is not parameter:
            raise RuntimeError(f"Reads and writes out of sync. Expected Parameter '{parameter}' but got '{resp_parameter}")
        if address != resp_address:
            raise RuntimeError(f"Reads and writes out of sync. Expected address '{address}' but got '{resp_address}")
        if resp_channel != channel:
            raise RuntimeError(f"Reads and writes out of sync. Expected channel '{channel}' but got '{resp_channel}")

        return value

    @usb_except
    def set(self, parameter, channel, value):
        """
        Write Single Location Command
            Number of bytes: 10
            Format: 0xA2 [addr] [data] 0x55
            Return Value: none
        Write Next Command
            Number of bytes: 6
            Format: 0xA3 [data] 0x55
            Return Value: none
        """
        if not isinstance(value, (int, float)):
            raise TypeError(f"Parameter values must be int or float not {type(value)}")

        address = self.build_address(parameter, channel)

        if parameter is Parameters.LOOP:
            value = struct.pack(NPointTipTiltController.endian + 'I', 1 if value else 0)
            self._send(b''.join([Commands.SET.value, address, value, self.endpoint]))
        else:
            value = struct.pack(NPointTipTiltController.endian + 'd', float(value))
            # Send value in two halves.
            self._send([b''.join([Commands.SET.value, address, value[:4], self.endpoint]),
                        b''.join([Commands.SECOND_MSG.value, value[4:], self.endpoint])])

    @usb_except
    def set_and_check(self, parameter, channel, value):
        self.set(parameter, channel, value)
        set_value = self.get(parameter, channel)
        if value != set_value:
            raise ValueError(f'Command was NOT successful : {value} != {set_value}.')  # RT error?
        self.log.debug(f'Command successful: {value} == {set_value}.')

    @usb_except
    def get_config(self):
        """Checks the feasible configurations for the device."""
        for cfg in self.instrument:
            self.log.info('Device config : ')
            self.log.info(cfg)
        
    @usb_except
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

        Read Array Command
            Number of bytes: 10
            Format: 0xA4 [addr] [numReads] 0x55
            Return Value: 0xA4 [addr] [data 1].....[data N] 0x55
        Write Single Location Command
            Number of bytes: 10
            Format: 0xA2 [addr] [data] 0x55
            Return Value: none
        Write Next Command
            Number of bytes: 6
            Format: 0xA3 [data] 0x55
            Return Value: none

        Returns:
            Command, Parameter, address, channel, data
        """

        # Parse command
        try:
            command = Commands(message[:4])
        except ValueError as error:
            raise NotImplementedError('Non implemented command found in message.') from error

        parameter = None
        address = None
        channel = None
        if command in (Commands.GET, Commands.SET):
            # Parse address
            address = message[4:8]

            # Parse channel
            int_address = struct.unpack(cls.endian + 'I',address)[0]
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
            data = struct.unpack(cls.endian + 'I', message[-8:-4])[0]
        elif command is Commands.GET:
            # For GET, message could be either that sent or that received. E.g., either of the following:
            # 0xA4 [addr] [numReads] 0x55
            # 0xA4 [addr] [data 1].....[data N] 0x55
            data_block = message[8:-4]
            data_block_byte_length = len(data_block)//4
            if data_block_byte_length == 1:
                data_type_fmt = 'I'
            elif data_block_byte_length == 2:
                data_type_fmt = 'd'
            else:
                raise NotImplementedError(f"Supports only 32b ints and 64b floats. Received {data_block_byte_length * 32}b data block.")
            data = struct.unpack(cls.endian + data_type_fmt, data_block)[0]
        else:
            raise NotImplementedError('Non implemented command found in message.')

        return command, parameter, address, channel, data

    @classmethod
    def _build_message(self, cmd_key, cmd_type, channel, value=None):
        """Builds the message to send to the controller. The messages
        must be 10 or 6 bytes, in significance increasing order (little
        endian.)
        The format of the message to write to a new location is :
        [1 byte type (0xA2)] [4 byte address] [4 byte int/first half of float]
        [1 byte sign off (0x55)]

        To write something else to the same location :
        [1 byte type (0xA3)] [4 byte message (second half of float)]
        [1 byte sign off]
        To read from a location :
        [1 byte type (0xA4)] [4 byte address] [4 byte numReads][1 byte sign off]

        Parameters
        ----------
        cmd_key : str
            The key to point toward the p/i/d_gain or loop.
        cmd_type : str
            Either "get" to return a message or "set" to write a command.
        channel : int
            1 or 2 for which channel.
        value : int/float, optional
            If it's writing a command, what value to set it to. This
            will fail if it needs a value and is not given one.
        Returns
        -------
        message : list of bytes
            An list of bytes messages. One if it's call to get a value
            or a simple int message, or two if it needs to write a float
            and use two messages.
        """

        cmd_dict = {'loop': 84, 'p_gain': 720, 'i_gain': 728, 'd_gain': 730}

        addr = 11830000 + 1000 * channel + cmd_dict[cmd_key]
        addr = '0x{}'.format(addr)

        # Note that the < specifies the little endian/signifigance increasing order here
        addr = struct.pack('<Q', int(addr, 16))

        # Now build message or messages
        message = []

        if cmd_type == 'get':
            if value is not None:
                import warnings
                warnings.warn('You specified a value but nothing will happen to it.')

            message.append(b'\xa4' + addr[:4] + b'\x02\x00\x00\x00\x55')

        elif cmd_type == 'set':
            if value is None:
                raise ValueError("Value is required.")

            if cmd_key == 'loop':
                if value not in [1, 0]:
                    raise ValueError("1 or 0 value is required for loop.")

                # Convert to hex
                val = struct.pack('<I', value)
                message.append(b'\xa2' + addr[:4] + val + b'\x55')

            elif cmd_key in ['p_gain', 'i_gain', 'd_gain']:
                if type(value) == int:
                    value = float(value)

                elif type(value) not in [float]:
                    raise TypeError("Int or float value is required for gain.")

                # Convert to hex double (64 bit)
                val = struct.pack('<d', value)

                message.append(b'\xa2' + addr[:4] + val[:4] + b'\x55')
                message.append(b'\xa3' + val[4:] + b'\x55')

            else:
                raise ValueError("cmd_key must be 'loop' or 'p/i/d_gain'.")
        else:
            raise NotImplementedError('cmd_type must be get or set.')

        return message
