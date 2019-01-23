## -- Controller interface for the newport picomotor. 
"""
This is certainly its own beast. (A small cute beast.)
The name of the game seems to be getting the IP address and 
giving it the ol' ping until the command goes through.

Authors
-------
Jules Fowler, 2019

"""

## -- IMPORTS
import os

from http.client import IncompleteRead
import numpy as np
from photutils import centroid_2dg
from urllib.parse import urlencode
from urllib.request import urlopen

## -- Let's go.

def maybe_some_error_handling?

class NewportPicomotor:
    """ This class handles all the picomotor stufff. """

    def __init__(self):
        # logging 4 days
        self.ip = ...

    def __enter__(self):
        return self

    def __exit__(self):
        # set dh to zero, zero
        # prob don't try to reset
        print('Byee.')

    def get_status(self):
        return

    def command(self):

        set_message = self._build_message(self, cmd_key, 'set', axis, value)
        get_message = self._build_message(self, cmd_key, 'get', axis)
        
        self._send_message(set_message)
        return

    def reset(self):
        
        message = self._build_message(self, 'reset', 'reset')
    

    def set_to_centroid(self, data, x_center=0, y_center=0, flip=False):
        """ Sets the home position to the 2d centroid.

        Parameters
        ----------
        data : np.array
            2D image array to check for the centroid position.
        x_center : float, optional
            Where the controller thinks the x_0 of the detector is. 
            Defaults to zero.
        y_center : float, optional 
            Where the controller thinks the y_0 of the detector is. 
            Defaults to zero.
        flip : bool, optional
            Whether or not the axis 1/2 is flipped from x/y. Defaults to 
            False.
        """
        if flip:
            x, y = y, x
        x, y = centroid_2dg(data)
        self.command('home_position', 'set', '1', x-x_center)
        self.command('home_position', 'set', '2', y-y_center)

    def _build_message(self, cmd_key, cmd_type, axis=None, value=None):
        """Build a message for the newport picomotor controller.

        Parameters
        ----------
        cmd_key : str
            The command and hand, like position, reset, etc.
        cmd_type : str
            The kind of command, whether to get, set, or reset.
        axis : str of int, optional
            The axis (1-4 are valid) to set. Defaults to None.
        value : str 
            """

        cmd_dict = {'home_position' : 'DH', 'exact_move' : 'PA', 
                    'relative_move' : 'PR', 'reset' : 'RS'}
        
        address = cmd_dict[cmd_key]
        
        if cmd_key == 'reset':
            if axis != None:
                # log warn
                print('Nothing will happen to the specified axis while we reset.')
            if value != None:
                # log warn
                print('Nothing will happen to the specified value while we reset.')

            message = address 

        if cmd_key == 'get':
            if axis == None:
                raise ValueError("This command requires an axis.")
            elif value != None:
                # log warn 
                print('Nothing will happen to the specified value while we check stuff.')
            else:
                message = '{}{}?'.format(axis, address)
        
        elif cmd_key == 'set': 
            if aixs == None:
                raise ValueError("This command requires an axis.")
            elif value != None:
                raise ValueError("This command requires a value.")
            elif cmd_key in ['exact_move', 'relative_move'] and np.abs(value) > 2147483647:
                raise ValueError('You can only move 2147483647 in any direction.')
            else:
                message = '{}{}{}'.format(axis, address, value)
            
        return message
    

    def _send_message(self, cmd_type):
        
        form_data = urlencode{'cmd': message, 'submit': 'Send'}
        binary_data = form_data.encode('ascii')

        html = urlopen('{}/cmd_send.cgi'.format(self.ip), cal_data)
        resp = html.split('Response')[-1]

        return resp
