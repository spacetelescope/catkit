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

from bs4 import BeautifulSoup
from http.client import IncompleteRead
import itertools
import numpy as np
import requests
from requests.exceptions import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from pyql.logging.logging_functions import configure_logging
from pyql.logging.logging_functions import log_info
from pyql.logging.logging_functions import log_fail


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
        # set ac to zero, zero
        # prob don't try to reset
        print('Byee.')

    def get_status(self)
        

    def command(self)

    def _build_message(self, cmd_key, cmd_type, axis=None, value=None):
        """Build a message for the newport picomotor controller.

        Parameters
        ----------
        cmd_key : str
            The command and hand, like acceleration, position, etc.
        cmd_type : str
            The kind of command, whether to get, set, or reset.
        axis : str of int, optional
            The axis (1-4 are valid) to set. Defaults to None.
        value : str 
            """

        cmd_dict = {'acceleration' : 'AC', 'home_position' : 'DH', 
                    'exact_move' : 'PA', 'relative_move' : 'PR', 
                    'reset' : 'RS'}
        
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
    

    def _send_message(self):
        
        form_data = urlencode{'cmd': message, 'submit': 'Send'}
        binary_data = form_data.encode('ascii')

        html = urlopen('{}/cmd_send.cgi'.format(self.ip), cal_data)
        resp = html.split('Response')[-1]

        return resp
