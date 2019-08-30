## -- Controller interface for the newport picomotor. 
"""
Interface for the newport picomotors. 
Checks the website spins up appropriately, and then holds
convenience functions to send commands to the motors, check 
the status, and try to put some error handling over top.

According to the manual, this should hold for models: 
8743-CL-various, 8745-PS

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
            raise Exception('Issues connecting to the webpage.') from e

    return wrapper

class NewportPicomotor:
    """ This class handles all the picomotor stufff. """

    def __init__(self, config_params):
        """ Initial function to set up logging and 
        set the IP address for the controller."""

        # Set IP address
        if config_params is None:
            config_file = os.environ.get('CATKIT_CONFIG')
            if config_file is None:
                raise NameError('No available config to specify npoint connection.')
            
            config = configparser.ConfigParser()
            config.read(config_file)
            self.ip = config.get('newport_picomotor_8743-CL_8745-PS', 'ip_address')
            self.max_step = config.get('newport_picomotor_8743-CL_8475_PS', 'max_step')
            self.timeout = config.get('newport_picomotor_8743-CL_8475_PS', 'timeout')

        else:
            self.ip = config_params['ip_address']
            self.max_step = config_params['max_step']
            self.timeout = config_params['timeout']

        str_date = str(datetime.datetime.now()).replace(' ', '_').replace(':', '_')
        self.logger = logging.getLogger('Newport-{}'.format(str_date))
        self.logger.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        log_file = 'newport_{}_{}.log'.format(self.ip, str_date)
        fh = logging.FileHandler(filename=log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)
        
        # Initialize some command parameters
        self.cmd_dict = {'home_position': 'DH', 'exact_move': 'PA', 
                         'relative_move': 'PR', 'reset': 'RS', 
                         'error_message': 'TB'}
        


        self.calibration = {} 

        try:
            urlopen('http://{}'.format(self.ip), timeout=timeout)
        except (IncompleteRead, HTTPError, Exception) as e:
            self.close_logger()
            raise OSError("The controller IP address is not responding.") from e

        self.logger.info('IP address : {}, is online, and logging instantiated.'.format(self.ip))

        # Test motor connections
        self.motor_dict = {}
        self.check_motors()

    def __enter__(self):
        """ Enter function to allow context management."""

        return self

    def __exit__(self, ex_type, ex_value, traceback):
        """ Exit function to open loop, reset parameters to 0, close the
        logging handler."""

        self.close()
    
    def __del__(self):
        """ Destructor with close behavior."""
        
        self.close()

    def close(self):
        """ Function for the close behavior. Return every parameter to zero
        and shut down the logging."""

        self.reset_controller()
        self.close_logger()

    def reset_controller(self):
        """Function to reset the controller behavior."""

        for cmd_key in ('home_position', 'exact_move'):
            for axis in '1234':
                self.command(cmd_key, axis, 0)
    
    def check_motors(self):
        """ Function to check if motors are online."""

        for motor in '1234':
            self.motor_dict[motor] = True
            message = self._build_message('error_message', 'get', '')
            response = self._send_message(message, 'get')
            self.motor_dict[motor] = 'Motor' not in response
            logging.info('Motor {} is {} online.'.format(motor, '' if success else 'NOT')

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
            Axis 1, 2, 3, 4.
        value : int
            Given an int,
            it will set the command to that value.
        """
        # Check on motor 
        if not self.motor_dict[str(axis)]:
            raise OSError('Motor {} is not plugged in. If you think it is, try checking the motors with ...'.format(axis))
        value = value
        set_message = self._build_message(cmd_key, 'set', axis, value)
        get_message = self._build_message(cmd_key, 'get', axis)
        
        if cmd_key == 'relative_move':
            initial_value = self._send_message(get_message, 'get') if cmd_key == 'relative_move' else 0
        else:
            initial_value = 0
        self._send_message(set_message, 'set')
        set_value = float(self._send_message(get_message, 'get')) - float(initial_value)
        
        if float(set_value) != value:
            self.logger.error('Something is wrong, {} != {}'.format(set_value, value)) 
         
        self.logger.info('Command sent. Action : {}. Axis : {}. Value : {}'.format(cmd_key, axis, value))
    
    def convert_move_to_pixel(self, img_before, img_after, move, axis):
        """ After two images taken some x_move or y_move apart, calculate how
        the picomoter move corresponds to pixel move.
        
        Parameters
        ----------
        img_before : np.array
            Image before move.
        img_after : np.array
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

        x1, y1 = centroid_1dg(img_before)
        x2, y2 = centroid_1dg(img_after)

        x_move = x1 - x2
        y_move = y1 - y2
        
        r = np.sqrt(x_move**2 + y_move**2)
        theta = np.arctan(y_move/x_move)
        
        r_ratio = r/move
        
        if axis in '13':
            delta_theta = theta - 0
        
        elif axis in '24':
            delta_theta = theta - np.pi/2
        
        else:
            raise NotImplementedError('Only axis 1 through 4 are defined.')
        
        self.calibration['r_ratio_{}'.format(axis)] = r_ratio
        self.calibration['delta_theta_{}'.format(axis)] = delta_theta
        
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
        
        address = self.cmd_dict[cmd_key]

        if cmd_key == 'reset':
            if axis != None:
                raise ValueError('No axis is needed for a reset.')
                
            if value != None:
                raise ValueError('No value is needed for a reset.')

            message = address 

        if cmd_type == 'get':
            if cmd_key == 'error_message' and axis != '':
                raise ValueError("No axis can be specified for an error check.")
            elif axis == None:
                raise ValueError("This command requires an axis.")
            elif value != None:
                raise ValueError('No value can be set during a status check.')
            message = '{}{}?'.format(int(axis), address)
        
        elif cmd_type == 'set': 
            if axis == None:
                raise ValueError("This command requires an axis.")
            elif value == None:
                raise ValueError("This command requires a value.")
            elif cmd_key in ['exact_move', 'relative_move'] and np.abs(value) > self.max_step:
                raise ValueError('You can only move {} in any direction.'.format(self.max_step))
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
            # The output will be nestled between --> and \\r
            response = resp.split('response')[1].split('-->')[1].split('\\r')[0]

            return response

