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
import datetime
import functools
import logging
import os

from http.client import IncompleteRead
import numpy as np
from photutils import centroid_2dg
from requests.exceptions import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

## -- Let's go.

def http_except(function):
    """Decorator to catch http/web exceptions."""

    @functools.wraps(function)
    def wrapper(self, *args, **kwargs):
        try:
            return function(self, *args, **kwargs)
        except (IncompleteRead, HTTPError) as e:
            self.logger.error("The page timed out with : {}.".format(e))
            raise Exception 

    return wrapper

class NewportPicomotor:
    """ This class handles all the picomotor stufff. """

    def __init__(self):
        """ Initial function to set up logging and 
        set the IP address for the controller."""

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
        
        # Set IP address 
        self.ip = '192.1168.192.151'

    def __enter__(self):
        """ Enter function to allow context management."""

        return self

    def __exit__(self):
        """ Exit function to return all settings to base."""
        
        for cmd_key in ('home_position', 'exact_move'):
            for axis in (1,2):
                self.command(cmd_key, axis, 0)
        
        self.logger.info('Everything has been reset. Enjoy your new life.')
    
    @http_except
    def get_status(self, axis):
        """Checks the status of the relative/absolute positions and home 
        positions for the given axis.
        
        Parameters
        ----------
        axis : int
            The axis to check.
        
        Returns
        -------
        state_dict : dictionary
            A dictionary of what each useful key is set to.
        """
        
        state_dict = {}
        for cmd_key in ('home_position', 'exact_move'):
            message = self._build_message(self, cmd_key, 'get', axis)
            value = self._send_message(message, 'get') 
            state_dict['{}_{}'.format(cmd_key, axis)] = value
            logging.info('For axis {}, {} is set to {}'.format(axis, cmd_key, value))
        
        return state_dict
    
    @http_except
    def command(self, cmd_key, axis, value):

        set_message = self._build_message(self, cmd_key, 'set', axis, value)
        get_message = self._build_message(self, cmd_key, 'get', axis)
        
        self._send_message(set_message, 'set')
        set_value = self._send_message(get_message, 'get')
        if cmd_key in ['home_position', 'absolute_move']: 
            if set_value != value:
                logging.warn('Something is wrong, {} != {}'.formatset_value, value) 
        else:
            logging.warn("There's not good way to check relative moves at this time.")
        
        logging.info('Command sent. Action : {}. Axis : {}. Value : {}'.format(cmd_key, axis, value))
        
    @http_except
    def reset(self):
        """Resets the controller."""
        
        message = self._build_message(self, 'reset', 'reset')
        self.__send_message(message, 'set')
        logging.info('Controller reset')

    @http_except
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
        
        logging.info('Centroid found at ({},{}). Resetting home position.'.format(x, y))
        
        self.command('home_position', 'set', 1, x-x_center)
        self.command('home_position', 'set', 2, y-y_center)
    
    def _build_message(self, cmd_key, cmd_type, axis=None, value=None):
        """Build a message for the newport picomotor controller.

        Parameters
        ----------
        cmd_key : str
            The command and hand, like position, reset, etc.
        cmd_type : str
            The kind of command, whether to get, set, or reset.
        axis : int, optional
            The axis (1-4 are valid) to set. Defaults to None.
        value : str 
        """

        cmd_dict = {'home_position' : 'DH', 'exact_move' : 'PA', 
                    'relative_move' : 'PR', 'reset' : 'RS'}
        
        address = cmd_dict[cmd_key]
        print(address)

        if cmd_key == 'reset':
            if axis != None:
                self.logger.info('Nothing will happen to the specified axis while we reset.')
                
            if value != None:
                self.logger.info('Nothing will happen to the specified value while we reset.')

            message = address 

        if cmd_type == 'get':
            if axis == None:
                self.logger.error("This command requires an axis.")
                raise ValueError("This command requires an axis.")
            elif value != None:
                self.logger.info('Nothing will happen to the specified value while we check stuff.')
            message = '{}{}?'.format(int(axis), address)
        
        elif cmd_type == 'set': 
            if axis == None:
                self.logger.error("This command requiers an axis.")
                raise ValueError("This command requires an axis.")
            elif value == None:
                self.logger.error("This command requires a value.")
                raise ValueError("This command requires a value.")
            elif cmd_key in ['exact_move', 'relative_move'] and np.abs(value) > 2147483647:
                self.logger.error('You can only move 2147483647 in any direction.')
                raise ValueError('You can only move 2147483647 in any direction.')
            else:
                message = '{}{}{}'.format(int(axis), address, int(value))
            
        return message
    
    def _send_message(self, cmd_type):
        
        form_data = urlencode({'cmd': message, 'submit': 'Send'})
        binary_data = form_data.encode('ascii')

        html = urlopen('{}/cmd_send.cgi'.format(self.ip), cal_data)
        resp = html.split('Response')[-1]
        
        if cmd_type == 'get':
            # Figure out how this is gonna look to extra the element
            resp = resp[0]
            return resp

    def convert_move_to_pixel(self, img1, img2, move, axis):
        """ After two images taken some x_move or y_move apart, calculate how
        the picomoter move corresponds to pixel move.
        
        Parameters
        ----------
        img1 : np.array
            Image before move.
        img2 : np.array
            Image after move.
        move : int
            How much the picomotor moved.
        axis : int
            What axis the picomotor moved on.
        
        Returns
        -------
        r : float
            The scalar distance of the move in pixels.
        theta : float
            The angle from x in radians. 
        r_ratio : float
            The ratio of the scalar distance in pixels and the picomotor move. 
        delta_theta : float
            The difference between the angle from x and the picomotor axis.
        """

        x1, y1 = centroid_2dg(img1)
        x2, y2 = centroid_2dg(img2)

        x_move = x1 - x2
        y_move = y1 - y2
        
        r = np.sqrt(x_move**2 + y_move**2)
        theta = np.arctan(y_move/x_move)
        
        r_ratio = r/move
        
        if axis == 1:
            delta_theta = theta - 0
        elif axis == 2:
            delta_theta = theta - np.pi/2
        else:
            raise NotImplementedError('Only axis 1 and axis 2 are defined.')
        
        self.r_ratio = r_ratio
        self.delta_theta = delta_theta

        return r, theta, r_ratio, delta_theta




