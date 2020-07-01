""" Interface for the nPoint Tip/Tilt closed-loop controller.
Connects to the controller via usb, and then sends and recieves hex
messages to send commands, check the status, and put error handling over
top.
"""

from collections import deque
import logging
import struct

import numpy as np

from catkit.hardware.npoint.nPointTipTiltController import Commands, Variables, nPointTipTiltController
from catkit.interfaces.Instrument import SimInstrument


class EmulatedLibUSB:
    @staticmethod
    def get_backend(find_library=None):
        pass


class PyusbNpointEmulator:
    """nPointTipTilt connection class. 

    This nPointTipTilt class acts as a useful connection and storage vehicle 
    for commands sent to the nPoint FTID LC400 controller. It has built in 
    functions that allow for writing commands, checking the status, etc. 
    By instantiating the nPointTipTilt object you find the LC400 controller 
    and set the default configuration. Memory managers in the back end 
    should close the connection when the time is right.
    """

    config_params = ('< SIMULATED CONFIGUARTION 1: 0 mA>',)
    # Create a reverse version of the command dictionary
    message_prefix = (50, 96, 164)
    message_suffix = (85,)
    channels = (1, 2)

    def __init__(self):
        """ Since we'll need to respond as if commands are being sent and we
        can read values, this is where we'll initialize some value stores that
        will get sent in emulated messages. """

        self.log = logging.getLogger(f"{self.__module__}.{self.__class__.__qualname__}")

        self.value_store = {f'{n}': {var: 0 for var in Variables} for n in self.channels}
        self.response_message = None
        self.message_stack = deque([])
        self.float_message_store = []

    def find(self, idVendor, idProduct):
        """ On hardware, locates device. In simulation, returns itself so we can keep going."""
        self.log.info('SIMULATED nPointTipTilt instantiated and logging online.')
        return self

    def __iter__(self):
        """ Simulated iteration to appeal to the ability to check the configuration modes with `get_config`. """
        for cfg in self.config_params:
            yield cfg
    
    def set_configuration(self, configuration=None):
        """ On hardware, sets nPoint to its default configuration. In simulation, no behavior necessary."""
        if configuration is not None:
            raise NotImplementedError("We don't have the ability to set or simulate non-default configuration.")

    def read(self, endpoint, message_length, timeout):
        """ On hardware, reads single message from device. In simulation, pulls most recent message that expected a response. """
        return self.response_message

    def write(self, endpoint, message, timeout):
        """ On hardware, writes a single message from device. In simulation,
        updates logical stored values. """

        self.message_stack.append(message)
        
        if Commands(message[0]) is Commands.SECOND_MSG:
            
            # This is the second half of a set message for float values.
            # This means there won't be an address to parse
            self.float_message_store[1] = message[1:-1]
            float_message = ''.join(self.float_message_store)
            val = struct.unpack('<d', float_message)[0]

            addr = self.message_stack.popleft()[1:3]
            # Pull a channel and key of the style ['0xnm_1', '0xm_2m_3']
            # Where n is the channel 
            # And m_1m_2m_3 make up a key
            key = hex(addr[1])[3] + hex(addr[0])[2:]
            channel = hex(addr[1])[2]
            self.value_store[channel][Variables(key)] = val
            self.log.info(f'Setting channel {channel} key {Variables(key)} to {val}')
        
        elif Commands(message[0]) is Commands.SET:

            # This is an int set or the first half of a float set
            addr = message[1:3]

            key = hex(addr[1])[3] + hex(addr[0])[2:]
            channel = hex(addr[1])[2]

            if Variables(key) is Variables.LOOP:
                # int set for open/close loop
                val = message[-5:-1]
                val = struct.unpack('<I', val)[0]
                
                self.value_store[channel][Variables.LOOP] = val
                self.log.info(f'Setting channel {channel} key {Variables(key)} to {val}')
                
            else:
                # float set for gain
                self.float_message_store[0] = message[-5:-1]

        elif Commands(message[0]) is Commands.GET:
            # This is get message and we want a response
            addr = message[1:3]
            cmd_key = Variables((addr[1])[3] + hex(addr[0])[2:])
            channel = hex(addr[1])[2]
            val = self.value_store[channel][cmd_key]
            if cmd_key is Variables.LOOP:
                # pack as an int and pad with zeros
                hex_val = struct.pack('<I', val)
                full_val = [hex_val[n] for n in range(len(hex_val))] + [0, 0, 0, 0]
            else:
                # pack as a double
                hex_val = struct.pack('<d', float(val))
                full_val = [hex_val[n] for n in range(len(hex_val))]
            
            full_address = [message[n] for n in range(1,5)]
            full_message = self.message_prefix + full_address + full_val + self.message_suffix
            self.response_message = np.array(full_message, dtype='B')
            
        else:
            raise NotImplementedError('Non implemented command message sent to nPoint simulator.')


class SimnPointTipTiltController(SimInstrument, nPointTipTiltController):
    """ Emulated version of the nPoint tip tilt controller. 
    Directly follows the npoint, except points to simlated USB connection
    library. """

    instrument_lib = PyusbNpointEmulator
    library_mapping = {'libusb0': EmulatedLibUSB, 'libusb1': EmulatedLibUSB}