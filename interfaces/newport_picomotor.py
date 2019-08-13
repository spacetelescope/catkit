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
from photutils import centroid_1dg
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
            raise Exception('{} : was caught due to issues connecting to the webpage.'.format(e))

    return wrapper

class NewportPicomotor:
    """ This class handles all the picomotor stufff. """

    def __init__(self):
        """ Initial function to set up logging and 
        set the IP address for the controller."""


        str_date = str(datetime.datetime.now()).replace(' ', '_').replace(':', '_')
        self.logger = logging.getLogger('Newport-{}'.format(str_date))
        self.logger.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        log_file = 'newport_interface_log_{}.log'.format(str_date)
        fh = logging.FileHandler(filename=log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)
        
        # Set IP address 
        self.ip = '192.168.192.151'
        try:
            urlopen('http://{}'.format(self.ip), timeout=60)
        except (IncompleteRead, HTTPError, Exception) as e:
            self.close_logger()
            raise NameError("The controller IP address is not responding.")

        self.logger.info('IP address online, and logging instantiated.')


    def __enter__(self):
        """ Enter function to allow context management."""

        return self

    def __exit__(self, ex_type, ex_value, traceback):
        """ Exit function to open loop, reset gain parameters to 0, close the
        logging handler, and maybe someday close the controller intelligently."""

        self.close()
    
    def __del__(self):
        """ Destructor with close behavior."""
        
        self.close()

    def close(self):
        """ Function for the close behavior. Return every parameter to zero
        and shut down the logging."""

        self.close_controller()
        self.close_logger()

    def close_controller(self):
        """Function for the close controller behavior."""

        for cmd_key in ('home_position', 'exact_move'):
            for axis in (1,2):
                self.command(cmd_key, axis, 0)
        
    def close_logger(self):
        """Function for the close logger behavior."""

        handlers = self.logger.handlers[:]
        for handler in handlers:
            handler.close()
            self.logger.removeHandler(handler)

    @http_except
    def command(self, cmd_key, axis, value):
        """ Function to send a command to the controller.

        Parameters
        ----------
        cmd_key : str
            The parameter to set, presently allows for 'home_position',
            'exact_move', or 'relative_move'.
        axis : int
            Axis 1, 2, (or potentially 3) for x/y/z, tip/tilt/piston.
        value : int/float/double
            Given any number (it will be converted to int regardless of type),
            it will set the command to that value.
        """
        value = round(value)
        set_message = self._build_message(cmd_key, 'set', axis, value)
        get_message = self._build_message(cmd_key, 'get', axis)
        
        if cmd_key == 'relative_move':
            init_value = self._send_message(get_message, 'get')
        else:
            init_value = 0
        self._send_message(set_message, 'set')
        set_value = float(self._send_message(get_message, 'get')) - float(init_value)
        
        if float(set_value) != value:
            self.logger.error('Something is wrong, {} != {}'.format(set_value, value)) 
         
        self.logger.info('Command sent. Action : {}. Axis : {}. Value : {}'.format(cmd_key, axis, value))
    
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

        x1, y1 = centroid_1dg(img1)
        x2, y2 = centroid_1dg(img2)

        x_move = x1 - x2
        y_move = y1 - y2
        
        r = np.sqrt(x_move**2 + y_move**2)
        theta = np.arctan(y_move/x_move)
        
        r_ratio = r/move
        
        if axis == 1:
            delta_theta = theta - 0
            self.r_ratio_1 = r_ratio
            self.delta_theta_1 = delta_theta
        elif axis == 2:
            delta_theta = theta - np.pi/2
            self.r_ratio_2 = r_ratio
            self.delta_theta_2 = delta_theta
        elif axis == 3:
            delta_theta = theta - 0
            self.r_ratio_3 = r_ratio
            self.delta_theta_3 = delta_theta
        elif axis ==4:
            delta_theta = theta - np.pi/2
            self.r_ratio_4 = r_ratio
            self.delta_theta_4 = delta_theta
        else:
            raise NotImplementedError('Only axis 1 through 4 are defined.')
        
        return r, theta, r_ratio, delta_theta
    
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
        for cmd_key in ('home_position', 'exact_move', 'relative_move'):
            
            message = self._build_message(cmd_key, 'get', axis)
            value = self._send_message(message, 'get') 
            state_dict['{}_{}'.format(cmd_key, axis)] = value
            self.logger.info('For axis {}, {} is set to {}'.format(axis, cmd_key, value))
        
        return state_dict
    
        
    @http_except
    def reset(self):
        """Resets the controller."""
        
        message = self._build_message('reset', 'reset')
        self._send_message(message, 'set')
        self.logger.info('Controller reset.')

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
        
        x, y = centroid_1dg(data)
        
        self.logger.info('Centroid found at ({},{}). Resetting home position.'.format(x, y))
        
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
        
        Returns
        -------
        message : str
            The message to send to the controller site.
        """
        
        cmd_dict = {'home_position' : 'DH', 'exact_move' : 'PA', 
                    'relative_move' : 'PR', 'reset' : 'RS'}
        
        address = cmd_dict[cmd_key]

        if cmd_key == 'reset':
            if axis != None:
                raise ValueError('No axis is needed for a reset.')
                
            if value != None:
                raise ValueError('No value is needed for a reset.')

            message = address 

        if cmd_type == 'get':
            if axis == None:
                raise ValueError("This command requires an axis.")
            elif value != None:
                raise ValueError('No value can be set during a status check.')
            message = '{}{}?'.format(int(axis), address)
        
        elif cmd_type == 'set': 
            if axis == None:
                raise ValueError("This command requires an axis.")
            elif value == None:
                raise ValueError("This command requires a value.")
            elif cmd_key in ['exact_move', 'relative_move'] and np.abs(value) > 2147483647:
                raise ValueError('You can only move 2147483647 in any direction.')
            else:
                message = '{}{}{}'.format(int(axis), address, int(value))
            
        return message
    
    def _send_message(self, message, cmd_type):
        """ Sends message to the controller.

        Parameters
        ----------
        message : str
            The message to send to the controller.
        cmd_type : str
            Get or set -- for whether to get the value or set the controller.

        Returns
        -------
        response : str of int
            If cmd_type == 'get' (and we want to take a value from the
            controller), it will return the value.
        """
        
        form_data = urlencode({'cmd': message, 'submit': 'Send'})
        with urlopen('http://{}/cmd_send.cgi?{}'.format(self.ip, form_data)) as html:
            resp = str(html.read())
        
        if cmd_type == 'get':
            # Pull out the response from the html on the page 
            response = resp.split('response')[1].split('-->')[1].split('\\r')[0]

            return response

