"""
Interface for the nPoint Tip/Tilt close loop controller. 
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

class PyusbNpointEmulator():
    """nPointTipTilt connection class. 

    This nPointTipTilt class acts as a useful connection and storage vehicle 
    for commands sent to the nPoint FTID LC400 controller. It has built in 
    functions that allow for writing commands, checking the status, etc. 
    By instantiating the nPointTipTilt object you find the LC400 controller 
    and set the default configuration. Memory managers in the back end 
    should close the connection when the time is right.
    """

    def __init__(self, **super_kwargs):
        """ Since we'll need to respond as if commands are being sent and we
        can read values, this is where we'll initialize some dummy values that
        will get send in fake hex messages. """

        self.log = logging.getLogger(f"{self.__module__}.{self.__class__.__qualname__}")
        self.dummy_values = {'{}'.format(n): {'loop':0, 'p_gain':0, 'i_gain':0,
            'd_gain':0} for n in (1, 2)}
        self.expected_response = None

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
    
    def set_configuration(self):
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
        cmd_dict = {293802116: (1, 'loop'),
                    293803808: (1, 'p_gain'),
                    293803816: (1, 'i_gain'),
                    293803824: (1, 'd_gain'),
                    293806212: (2, 'loop'),
                    293807904: (2, 'p_gain'),
                    293807912: (2, 'i_gain'),
                    293807920: (2, 'd_gain'),
                    0: (0, 'second half of gain update')}

        # Do some backwards message parsing
        # Make them into strings of the numbers that map to command key and channel
        address = message[1:5]
        int_address = struct.unpack('<I', address)[0]
        try:
            channel, cmd_key = cmd_dict[int_address] 
        except KeyError:
            if int(str(int_address)[:3]) == 107:
                channel, cmd_key = cmd_dict[0]
            
        if message[0] == 164:
            # This is get message and we want a response
            self.log.info('Simulated response will not pass value check.')
            self.log.info('The stored value for {} is {}'.format(cmd_key,
                self.dummy_values[str(channel)][cmd_key]))
            expected_response = np.array([50, 96, 164, 32, 23, 131, 17, 0, 0, 0, 0, 0, 0, 0, 0, 85], dtype='B')
            self.expected_response = expected_response
        
        elif message[0] == 162:
            # This is a set message and the message isn't spoofed well enough
            # for now.
            pass
        elif message[0] == 163:
            # This is the second half of a set message for float values.
            pass
        else:
            raise NotImplementedError('Not implemented command message sent to nPoint simulator.')


class SimnPointTipTiltController(SimInstrument, nPointTipTiltController):
    """ Emulated version of the nPoint tip tilt controller. 
    Directly follows the npoint, except points to simlated USB connection
    library. """

    instrument_lib = PyusbNpointEmulator
