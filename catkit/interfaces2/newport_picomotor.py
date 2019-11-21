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
import configparser
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

    def __init__(self, motor_count, controller_count, ip=None, max_step=None, timeout=None, home_reset=True):
        """ Initial function to set up logging and 
        set the IP address for the controller. Anything set to None will attempt to
        pull from the config file.
        
        Parameters
        ----------
        motor_count : int
            Number of connected motors.
        controller_count : int
            Number of daisy chained controllers.
        ip : string
            The IP address for the controller. Defaults to None.
        max_step : float
            The max step the controller can take. Defaults to None. 
        timeout : float
            The timeout before the urlopen call gives up. Defaults to None.
        home_reset : bool
            Whether or not to reset to the home position on controller close.
            Defaults to True.
        """
        
        # Build a list of motors and controllers. 
        self.motors = [n for n in range(1, motor_count+1)]
        self.controllers = [None] + [n for n in range(2, controller_count+1)]

        # Set IP address
        if None in [ip, max_step, timeout]:
            config_path = os.environ.get('CATKIT_CONFIG')
            if config_path is None:
                raise OSError('No available config to specify picomotor connection.')
            
            config = configparser.ConfigParser()
            config.read(config_path)
        
        self.ip = config.get('newport_picomotor_8743-CL_8745-PS', 'ip') if ip is None else ip
        self.max_step = config.get('newport_picomotor_8743-CL_8745-PS', 'max_step') if max_step is None else max_step
        self.timeout = config.get('newport_picomotor_8743-CL_8745-PS', 'timeout') if timeout is None else timeout
        self.home_reset = config.get('newport_picomotor_8743-CL_8745-PS', 'home_reset') if home_reset is None else home_reset

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
            urlopen('http://{}'.format(self.ip), timeout=self.timeout)
        except (IncompleteRead, HTTPError, Exception) as e:
            self.close_logger()
            raise OSError("The controller IP address is not responding.") from e

        self.logger.info('IP address : {}, is online, and logging instantiated.'.format(self.ip))
        
        # Save current position as home.
        for daisy in self.controllers:
            for axis in self.motors:
                self.command('home_position', int(axis), 0, daisy_key=daisy)
                self.logger.info('Current position saved as home.')


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
        
        if self.home_reset:
            self.reset_controller()
        self.close_logger()

    def reset_controller(self):
        """Function to reset the motors to where they started (or were last reset.)"""
        for daisy_key in self.controllers: 
            for axis in self.motors:
                self.command('exact_move', int(axis), 0, daisy_key=daisy_key)
                self.command('home_position', int(axis), 0, daisy_key=daisy_key)
                self.logger.info('Controller reset.')
        
    def close_logger(self):
        """Function for the close logger behavior."""

        handlers = self.logger.handlers[:]
        for handler in handlers:
            handler.close()
            self.logger.removeHandler(handler)

    @http_except
    def command(self, cmd_key, axis, value, daisy_key=None):
        """ Function to send a command to the controller.

        Parameters
        ----------
        cmd_key : str
            The parameter to set, presently allows for 'home_position',
            'exact_move', 'relative_move', or 'error_message'.
        axis : int
            Axis 1, 2, 3, 4.
        value : int
            Given an int, it will set the command to that value.
        daisy_key : int
            If the controller is daisy chained, where in the hierarchy we are. 
            If commands only to the master controller, no prefix is needed,
            defaults to None.
        """
        
        set_message = self._build_message(daisy_key, cmd_key, 'set', axis, value)
        get_message = self._build_message(daisy_key, cmd_key, 'get', axis)
        
        initial_value = self._send_message(get_message, 'get') if cmd_key == 'relative_move' else 0
        
        self._send_message(set_message, 'set')
        set_value = float(self._send_message(get_message, 'get')) - float(initial_value)
        
        if float(set_value) != value:
            self.logger.error('Something is wrong, {} != {}'.format(set_value, value)) 
         
        self.logger.info('Command sent. Action : {}. Axis : {}. Value : {}. Controller : {}.'.format(cmd_key, axis, value, daisy_key))
    
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
    def get_status(self, axis, daisy_key=None):
        """Checks the status of the relative/absolute positions and home 
        positions for the given axis.
        
        Parameters
        ----------
        axis : int
            The axis to check.
        daisy_key : int
            Where in the hierarchy the command falls. Defaults to None for
            master controller. 
        Returns
        -------
        state_dict : dictionary
            A dictionary of what each useful key is set to.
        """
        
        state_dict = {}
        for cmd_key in ('home_position', 'relative_move'):
            
            message = self._build_message(daisy_key, cmd_key, 'get', axis)
            value = self._send_message(message, 'get') 
            state_dict['{}_{}'.format(cmd_key, axis)] = value
            daisy_insert = '' if daisy_key is None else 'for chain {}'.format(daisy_key)
            self.logger.info('For axis {}, {} is set to {}'.format(axis, daisy_insert, cmd_key, value))
        
        return state_dict
        
    @http_except
    def reset(self, daisy_key=None):
        """Resets the controller."""
        
        message = self._build_message('reset', 'reset', daisy_key=daisy_key)
        self._send_message(message, 'set')
        self.logger.info('Controller reset.')

    def _build_message(self, cmd_key, cmd_type, daisy_key=None, axis=None, value=None):
        """Build a message for the newport picomotor controller.

        Parameters
        ----------
        cmd_key : str
            The command and hand, like position, reset, etc.
        cmd_type : str
            The kind of command, whether to get, set, or reset.
        axis : int, optional
            The axis (1-4 are valid) to set. Defaults to None.
        daisy_key : int, None
            Which controller in the master/slave hierarchy.
        value : str 
        
        Returns
        -------
        message : str
            The message to send to the controller site.
        """
        if daisy_key is None or isinstance(daisy_key, int):
            daisy_prefix = "{}>".format(daisy_key) if daisy_key else ""
        else:
            raise TypeError("The 'daisy_key' requires an integer or None input.")

        address = daisy_prefix + self.cmd_dict[cmd_key]

        if cmd_key == 'reset':
            if axis is not None:
                raise ValueError('No axis is needed for a reset.')
                
            if value is not None:
                raise ValueError('No value is needed for a reset.')

            message = address 

        if cmd_type == 'get':
            if cmd_key == 'error_message' and axis is not None:
                raise ValueError("No axis can be specified for an error check.")
            elif axis is None or not isinstance(axis, int):
                raise ValueError("This command requires an integer axis.")
            elif value is not None:
                raise ValueError('No value can be set during a status check.')
            message = '{}{}?'.format(axis, address)
        
        elif cmd_type == 'set': 
            if axis is None or not isinstance(axis, int):
                raise ValueError("This command requires an integer axis.")
            elif value is None or not isinstance(value, int):
                raise ValueError("This command requires an integer value.")
            elif cmd_key in ['exact_move', 'relative_move'] and np.abs(value) > self.max_step:
                raise ValueError('You can only move {} in any direction.'.format(self.max_step))
            else:
                message = '{}{}{}'.format(axis, address, value)
            
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
        with urlopen('http://{}/cmd_send.cgi?{}'.format(self.ip, form_data), timeout=self.timeout) as html:
            resp = str(html.read())
        
        if cmd_type == 'get':
            # Pull out the response from the html on the page 
            # The output will be nestled between --> and \\r
            response = resp.split('response')[1].split('-->')[1].split('\\r')[0]

            return response

