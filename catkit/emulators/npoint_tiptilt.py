"""
Interface for the nPoint Tip/Tilt close loop controller. 
Connects to the controller via usb, and then sends and recieves hex
messages to send commands, check the status, and put error handling over
top. 
"""

## -- IMPORTS

import configparser
import datetime
import functools
import logging
import os
import struct
import warnings

from numpy import double



## -- FUNCTIONS and FIDDLING 

class PyusbNpointEmulator():
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

        self.dummy_values = {'{}'.format(n): {'loop':0, 'p_gain':0, 'i_gain':0,
            'd_gain':0} for n in ('1', '2')}
        self.expected_response = ''

    def find(self, vendor_id, product_id):
        """ On hardware, locates device. In simulation, returns itself so we
        can keep going."""

        self.logger.info('SIMULATED nPointTipTilt instantiated and logging online.')
        
        return self

    def __iter__(self):
        """ Simulated iteration to appeal to the ability to check the
        configuration modes with ``get_config``. """

        for cfg in ['< SIMULATED CONFIGUARTION 1: 0 mA>']:
            yield cfg
    
    def set_configuration():
        """ On hardware, sets nPoint to its defaul configuration. In
        simulation, no behavior necesarry."""
        pass
    
    def read(self, endpoint, message_length, timeout):
        """ On hardware, reads single message from device. In simulation, pulls
        most recent message that expected a response. """
       
        return self.expected_response

    def write(self, endpoint, message, timeout):
        """ On hardware, writes a single message from device. In simulation,
        updates dummy values. """
        
        cmd_dict = {'084': 'loop', '720': 'p_gain', '728': 'i_gain', '730': 'd_gain'}

        # Do some backwards message parsing
        # Make them into strings of the numbers that map to command key and channel
        address = str(message[2:4]).split('\\x')
        channel = address[1][0]
        cmd_val = addres[1][1] + addres[2][:-1]
        cmd_key = cmd_dict[cmd_val] 
        
        if message[0] == 164:
            # This is get message and we want a response
            self.logger.info('Simulated response will not pass value check.')
            self.logger.info('The stored value for {} is {}'.format(cmd_key,
                self.dummy_values[channel][cmd_key]))
            expected_response = struct.pack('<Q', int(b'0x0000000000000000', 16))
            self.expected_response = expected_response
        elif message[1] == 162:
            # This is a set message and the message isn't spoofed well enough
            # for now.
            pass

        else:
            raise NotImplementedError('Not implemented message sent to nPoint
            simulator.')


class SimnPointTipTiltController(SimInstrument, nPointTipTiltController):
    """ Emulated version of the nPoint tip tilt controller. 
    Directly follows the npoint, except points to simlated USB connection
    library. """

    instrument_lib = PyusbNpointEmulator
