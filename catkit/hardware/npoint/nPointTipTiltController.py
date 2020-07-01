"""
Interface for the nPoint Tip/Tilt closed loop controller. 
Connects to the controller via usb, and then sends and recieves hex
messages to send commands, check the status, and put error handling over
top. 

In order to connect to the physical box, you'll need libusb appropriately
installed and have the driver for you machine set : Ex 
CATKIT_LIBUSB_PATH = 'C:\\Users\\HICAT\\Desktop\\libusb-win32-bin-1.2.6.0\\bin\\amd64\\libusb0.dll'
"""



## -- IMPORTS

import enum
import functools
import os
import struct
import time
import warnings

from numpy import double

from usb.backend import libusb0, libusb1
import usb.core
import usb.util

from catkit.interfaces.ClosedLoopController import ClosedLoopController


class Variables(enum.Enum):
    LOOP = '084'
    P_GAIN = '720'
    I_GAIN = '728'
    D_GAIN = '730'


class Commands(enum.Enum):
    SET = 162
    SECOND_MSG = 163
    GET = 164

## -- FUNCTIONS and FIDDLING 

# Decorator with error handling
def usb_except(function):
    """Decorator that catches PyUSB errors."""

    @functools.wraps(function)
    def wrapper(self, *args, **kwargs):
        try:
            return function(self, *args, **kwargs)
        except usb.core.USBError as e:
            raise Exception('USB connection error.') from e

    return wrapper


class nPointTipTiltController(ClosedLoopController):
    """nPointTipTiltController connection class. 

    This nPointTipTilt class acts as a useful connection and storage vehicle 
    for commands sent to the nPoint FTID LC400 controller. It has built in 
    functions that allow for writing commands, checking the status, etc. 
    By instantiating the nPointTipTilt object you find the LC400 controller 
    and set the default configuration. Memory managers in the back end 
    should close the connection when the time is right.
    """
    
    instrument_lib = usb.core

    # Define this library mapping as a static attribute.
    library_mapping = {'libusb0': libusb0, 'libusb1': libusb1}

    def initialize(self, vendor_id, product_id, library_path=None, library='libusb0'):
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

    def _build_message(self, var, command, channel, value=None):
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
        var : Variables enum
            The key to point toward the p/i/d_gain or loop.
        command : Commands enum
            Either Commands.GET to return a message or Commands.SET to write a command.
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

        addr = 11830000 + 1000 * channel + var.value
        addr = f'0x{addr}'
        
        # Note that the < specifies the little endian/significance increasing order here
        addr = struct.pack('<Q', int(addr, 16))

        # Now build message or messages 
        message = []

        if command is Commands.GET:
            if value is not None:
                warnings.warn('You specified a value but nothing will happen to it.')
            
            message.append(b'\xa4' + addr[:4] + b'\x02\x00\x00\x00\x55')

        elif command is Commands.SET:
            if value is None:
                raise ValueError("Value is required.")

            if var is Variables.LOOP:
                if value not in (1, 0):
                    raise ValueError("1 or 0 value is required for loop.")

                # Convert to hex
                val = struct.pack('<I', value)
                message.append(b'\xa2' + addr[:4] + val + b'\x55')

            elif var in Variables:
                if type(value) == int:
                    value = float(value)

                elif type(value) not in [float, double]:
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
    
    def _close(self):
        """Function for the close controller behavior."""

        for channel in [1, 2]:
            for var in Variables:
                self.command(var, channel, 0)

    def _open(self):
        """ Open function to connect to device. """

        # Instantiate the device
        self.instrument = self.instrument_lib.find(idVendor=self.vendor_id, idProduct=self.product_id, backend=self.backend)
        if self.instrument is None:
            raise NameError(f"Go get the device sorted you knucklehead.\nVendor id {self.vendor_id} and product id {self.product_id} could not be found and connected.")
             
        # Set to default configuration -- for LC400 this is the right one.
        self.dev = self.instrument # For legacy purposes
        self.instrument.set_configuration()
        self.log.info('nPointTipTilt instantiated and logging online.')
        
        return self.instrument

    def _read_response(self, response_type, return_timer=False, max_tries=10):
        """Read response from controller.

        Parameters
        ----------
        response_type : str
            '<I' or '<d', for an integer or double expected response.
        return_timer : bool, optional 
            Whether or not to return the tries and timing info.
        max_tries : int, optional
            How many times to check for a response. Set to 10.

        Returns
        -------
        value : int/float
            The int or float being sent.
        time_elapsed : float
            How long it took to read, only returned if return_timer=True.
        tries : int
            How many times it checked the message, only returned if
            return_timer=True.
        """

        resp = ''
        tries = 0
        
        start = time.time()
        
        # The junk message is 3 characters, so look for a longer one.
        
        endpoint = 0x81
        message_length = 100
        timeout = 1000
        while len(resp) < 4 and tries < max_tries:
            resp = self.instrument.read(endpoint, message_length, timeout) 
            tries += 1 
        time_elapsed = time.time() - start
        
        if len(resp) < 4:
            raise ValueError("No response was ever read.")
            
        else:
        
            # Value is never more than 8 bits, so grab those last ones
            val = resp[7:-1]
            if response_type == '<I':
                value = struct.unpack(response_type, val[:4])
            else:
                value = struct.unpack(response_type, val)
            # Value will be a 1D tuple and we want the value
            value = value[0]

            if return_timer:
                return value, time_elapsed, tries
            else:
                return value
    
    def _send_message(self, msg):
        """Send the message to the controller.

        Parameters
        ----------
        msg : list of bytes
            A controller ready message or messages.
        """
        
        endpoint = 0x02
        timeout = 100
        for message in msg:
            self.instrument.write(endpoint, message, timeout)
    
    @usb_except
    def command(self, var, channel, value):
        """Function to send a command to the controller and read back 
        to make sure it matches. 

        Parameters
        ----------
        var : Commands enum
            Whether to set the "loop" or "p/i/d_gain".
        channel : int
            What channel to set.
        value : int/flot
            What value to set.
        """

        set_message = self._build_message(var, Commands.SET, channel, value)
        get_message = self._build_message(var, Commands.GET, channel)

        self._send_message(set_message)
        self._send_message(get_message)
        if var is Variables.LOOP:
            response_type = '<I'
        else:
            response_type = '<d'
        set_value, time_elapsed, tries = self._read_response(response_type, return_timer=True)
        
        self.log.info(f'It took {time_elapsed} seconds and {tries} tries for the message to return.')
        if value == set_value:
            self.log.info(f'Command successful: {value} == {set_value}.')
        else:
            raise ValueError(f'Command was NOT sucessful : {value} != {set_value}.')

    @usb_except
    def get_config(self):
        """Checks the feasible configurations for the device."""
        
        for cfg in self.instrument:
            self.log.info('Device config : ')
            self.log.info(cfg)
        
    @usb_except
    def get_status(self, channel):
        """Checks the status of the loop, and p/i/d_gain for 
        the specified channel.

        Parameters
        ----------
        channel : int
            The channel to check.

        Returns
        -------
        value_dict : dict
            A dictionary with a setting for each parameter.
        """
        
        value_dict = {}
        self.log.info(f"For channel {channel}.")
        for var in Variables:
            self._send_message(self._build_message(var, Commands.GET, channel))
            if var is Variables.LOOP:
                response_type = '<I'
            else:
                response_type = '<d'
            value = self._read_response(response_type)
            self.log.info(f"For parameter : {var} the value is {value}")
            value_dict[var] = value

        return value_dict 


