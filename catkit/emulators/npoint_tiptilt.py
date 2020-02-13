""" Interface for the nPoint Tip/Tilt close loop controller. 
Connects to the controller via usb, and then sends and recieves hex
messages to send commands, check the status, and put error handling over
top. 
"""

## -- IMPORTS

import logging
import struct

import numpy as np

from catkit.hardware.npoint.nPointTipTiltController import nPointTipTiltController
from catkit.interfaces.Instrument import SimInstrument


## -- FUNCTIONS and FIDDLING 

class PyusbNpointEmulator:
    """nPointTipTilt connection class. 

    This nPointTipTilt class acts as a useful connection and storage vehicle 
    for commands sent to the nPoint FTID LC400 controller. It has built in 
    functions that allow for writing commands, checking the status, etc. 
    By instantiating the nPointTipTilt object you find the LC400 controller 
    and set the default configuration. Memory managers in the back end 
    should close the connection when the time is right.
    """

    def __init__(self):
        """ Since we'll need to respond as if commands are being sent and we
        can read values, this is where we'll initialize some dummy values that
        will get send in fake hex messages. """

        self.log = logging.getLogger(f"{self.__module__}.{self.__class__.__qualname__}")
        self.dummy_values = {f'{n}': {'loop':0, 'p_gain':0, 'i_gain':0, 'd_gain':0} for n in (1, 2)}
        self.commands = {'get': 164, 'set': 162, 'second_msg': 163}
        
        self.expected_response = None
        self.last_message = None
        self.second_to_last_message = None
        self.first_half_float = None
        self.second_half_float = None

    def find(self, idVendor, idProduct):
        """ On hardware, locates device. In simulation, returns itself so we
        can keep going."""

        self.log.info('SIMULATED nPointTipTilt instantiated and logging online.')
        return self

    def __iter__(self):
        """ Simulated iteration to appeal to the ability to check the
        configuration modes with ``get_config``. """

        for cfg in ['< SIMULATED CONFIGUARTION 1: 0 mA>']:
            yield cfg
    
    def set_configuration(self, configuration=None):
        """ On hardware, sets nPoint to its defaul configuration. In
        simulation, no behavior necesarry."""
        
        if configuration is not None:
            raise NotImplementedError("We don't have the ability to set or simulate non-default configuration.")
        pass
    
    def read(self, endpoint, message_length, timeout):
        """ On hardware, reads single message from device. In simulation, pulls
        most recent message that expected a response. """
       
        return self.expected_response


    def write(self, endpoint, message, timeout):
        """ On hardware, writes a single message from device. In simulation,
        updates dummy values. """
        
        # Create a reverse version of the command dictionary
        cmd_dict = {'084': 'loop', '720': 'p_gain', '728':  'i_gain', '730': 'd_gain'}
        
        # Set last and second to last messages
        self.second_to_last_message = self.last_message
        self.last_message = message
        
        if message[0] == self.commands['second_msg']:
            
            # This is the second half of a set message for float values.
            # This means there won't be an address to parse
            self.second_half_float = message[1:-1]
            float_message = self.first_half_float + self.second_half_float
            val = struct.unpack('<d', float_message)[0]

            addr = self.second_to_last_message[1:3]
            # Pull a channel and key of the style ['0xnm_1', '0xm_2m_3']
            # Where n is the channel 
            # And m_1m_2m_3 make up a key
            key = hex(addr[1])[3] + hex(addr[0])[2:]
            channel = hex(addr[1])[2]
            self.dummy_values[channel][cmd_dict[key]] = val
            self.log.info(f'Setting channel {channel} key {cmd_dict[key]} to {val}')
        
        elif message[0] == self.commands['set']:

            # This is an int set or the first half of a float set
            addr = message[1:3]

            key = hex(addr[1])[3] + hex(addr[0])[2:]
            channel = hex(addr[1])[2]

            if key == '084':
                # int set for open/close loop
                val = message[-5:-1]
                val = struct.unpack('<I', val)[0]
                
                self.dummy_values[channel]['loop'] = val
                self.log.info(f'Setting channel {channel} key {cmd_dict[key]} to {val}')
                
            else:
                # float set for gain
                self.first_half_float = message[-5:-1]

        
        elif message[0] == self.commands['get']:
            # This is get message and we want a response
            addr = message[1:3]
            cmd_key = cmd_dict[hex(addr[1])[3] + hex(addr[0])[2:]]
            channel = hex(addr[1])[2]
            val = self.dummy_values[channel][cmd_key]
            if cmd_key == 'loop':
                # pack as an int and pad with zeros
                hex_val = struct.pack('<I', val)
                full_val = [hex_val[n] for n in range(len(hex_val))] + [0, 0, 0, 0]
            else:
                # pack as a double
                hex_val = struct.pack('<d', float(val))
                full_val = [hex_val[n] for n in range(len(hex_val))]
            
            full_address = [message[n] for n in range(1,5)]
            full_message = [50, 96, 164] + full_address + full_val + [85]
            self.expected_response = np.array(full_message, dtype='B')
            
        else:
            raise NotImplementedError('Non implemented command message sent to nPoint simulator.')


class SimnPointTipTiltController(SimInstrument, nPointTipTiltController):
    """ Emulated version of the nPoint tip tilt controller. 
    Directly follows the npoint, except points to simlated USB connection
    library. """

    instrument_lib = PyusbNpointEmulator
