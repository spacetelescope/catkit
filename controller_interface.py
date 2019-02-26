## -- IMPORTS

import datetime
import functools
import logging
import os
import struct
import time
import warnings

from numpy import double
import usb.core
import usb.util


## -- FUNCTIONS and FIDDLING

# Decorator with error handling
def usb_except(function):
    """Decorator that catches PyUSB errors."""

    @functools.wraps(function)
    def wrapper(self, *args, **kwargs):
        try:
            return function(self, *args, **kwargs)
        except usb.core.USBError as e:
            self.logger.error("There's a timeout or a busy resource.")
            self.logger.error(e)
            raise e

    return wrapper


class Controller():

    """Controller connection class. 

    This Controller class acts as a useful connection and storage vehicle 
    for commands sent to the nPoint FTID LC400 controller. It has built in 
    functions that allow for writing commands, checking the status, etc. 
    By instantiating the Controller object you find the LC400 controller 
    and set the default configuration. Memory managers in the back end 
    should close the connection when the time is right.
    
    """

    def __init__(self):

        """Initial function to configure logging and find the device."""
        
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        log_file = os.path.join('.', 'controller_interface_log_{}.txt'.format(
            str(datetime.datetime.now()).replace(' ', '_').replace(':', '_')))
        fh = logging.FileHandler(filename=log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)
        
        # Instantiate the device
        # Vendor ID and Product ID for our specific controller for now
        vendor_id = 1027
        product_id = 24596
        self.dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
        if self.dev == None:
            self. logger.error('There was no device.')
            raise NameError("Go get the device sorted you knucklehead.")
        self.logger.info('Controller instantiated.')
        
        # Set to default configuration -- for LC400 this is the right one.
        self.dev.set_configuration()

    def __enter__(self):
        """ Enter function to allow for context management."""
        
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        """ Exit function to open loop and do other things someday?"""
        for channel in [1, 2]:
            for key in ["loop", "p_gain", "i_gain", "d_gain"]:
                self.command(key, channel, 0)

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
        message : array of bytes
            An array of bytes messages. One if it's call to get a value 
            or a simple int message, or two if it needs to write a float 
            and use two messages.
        """
        
        cmd_dict = {'loop': 84, 'p_gain': 720, 'i_gain': 728, 'd_gain': 730}

        addr = 11830000 + 1000*channel + cmd_dict[cmd_key]
        addr = '0x{}'.format(addr)
        
        # Note that the < specifies the little endian/signifigance increasing order here
        addr = struct.pack('<Q', int(addr, 16))

        # Now build message or messages 
        message = []

        if cmd_type == 'get':
            if value != None:
                warnings.warn('You specified a value but nothing will happen to it.')
            
            message.append(b'\xa4' + addr[:4] + b'\x02\x00\x00\x00\x55')

        elif cmd_type == 'set':
            if value == None:
                self.logger.error('There was no value set for this command.')
                raise ValueError("Value is required.")

            if cmd_key == 'loop':
                if value not in [1,0]:
                    self.logger.error('Loop requires a 1/0 value.')
                    raise ValueError("1 or 0 value is required for loop.")

                # Convert to hex
                val = struct.pack('<I', value)
                message.append(b'\xa2' + addr[:4] + val + b'\x55')

            elif cmd_key in ['p_gain', 'i_gain', 'd_gain']:
                if type(value) == int:
                    value = float(value)

                elif type(value) not in [float, double]:
                    self.logger.error('Gain requires float/int value.')
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
            resp = self.dev.read(endpoint, message_length, timeout) 
            tries += 1 
        time_elapsed = time.time() - start
        
        if len(resp) < 4:
            logging.error("No response was ever read.")
            raise ValueError("No response was ever read.")
            
        else:
            # Pull the address, which starts after 3 junk characters
            addr = resp[3:7]
            address = struct.unpack('<I', addr)
        
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
            self.dev.write(endpoint, message, timeout)
        
    
    @usb_except
    def command(self, cmd_key, channel, value):
        """Function to send a command to the controller and read back 
        to make sure it matches. 

        Parameters
        ----------
        cmd_key : str
            Whether to set the "loop" or "p/i/d_gain".
        channel : int
            What channel to set.
        value : int/flot
            What value to set.
        """

        set_message = self._build_message(cmd_key, "set", channel, value)
        get_message = self._build_message(cmd_key, "get", channel)

        self._send_message(set_message)
        self._send_message(get_message)
        if cmd_key == 'loop':
            response_type = '<I'
        else:
            response_type = '<d'
        set_value, time_elapsed, tries = self._read_response(response_type, return_timer=True)
        
        self.logger.info('It took {} seconds and {} tries for the message to return.'.format(time_elapsed, tries))
        if value == set_value:
            self.logger.info('Command successful: {} == {}.'.format(value, set_value))
        else:
            self.logger.info('Command NOT successful : {} != {}.'.format(value, set_value))
        
    @usb_except
    def get_config(self):
        """Checks the feasible configurations for the device."""
        
        for cfg in self.dev:
            self.logger.info('Device config : ')
            self.logger.info(cfg)
        

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

        read_msg = {'p_gain': self._build_message('p_gain', 'get', channel),
                    'i_gain': self._build_message('i_gain', 'get', channel),
                    'd_gain': self._build_message('d_gain', 'get', channel),
                    'loop': self._build_message('loop', 'get', channel)}
        
        value_dict = {}
        self.logger.info("For channel {}.".format(channel))
        for key in read_msg:
            self._send_message(read_msg[key])
            if key == 'loop':
                response_type = '<I'
            else:
                response_type = '<d'
            value = self._read_response(response_type)
            self.logger.info("For parameter : {} the value is {}".format(key, value))
            value_dict[key] = value

        return value_dict 



## -- MAIN with ex
if __name__ == "__main__":
    
    # Quick demo of doing something..
    ctrl = Controller()
    
