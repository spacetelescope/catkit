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
import functools

from http.client import IncompleteRead
import numpy as np
from photutils.centroids import centroid_1dg, centroid_2dg
from requests.exceptions import HTTPError
import urllib
from urllib.parse import urlencode

from catkit.interfaces.MotorController2 import MotorController2
import catkit.util

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

class NewportPicomotorController(MotorController2):
    """ This class handles all the picomotor stufff. """
    
    instrument_lib = urllib.request

    def initialize(self, ip, max_step, timeout, daisy, sleep_per_step=0.0005, 
            calibration=None, home_reset=True, centroid_method=None):
        """ Initial function set the IP address for the controller. Anything set to None will attempt to
        pull from the config file.
        
        Parameters
        ----------
        ip : string
            The IP address for the controller.
        max_step : float
            The max step the controller can take. 
        timeout : float
            The timeout before the urlopen call gives up.
        daisy : int
            The oridinal of daisy chained controller. I.e. 0 for the master
            controller, and then 2, 3, and so on.  
        calibration : dict, optional
            Precalculated calibration parameters. Default to None to
            intialize empty.
        home_reset : bool, optional
            Whether or not to reset to the home position on controller close.
            Defaults to True.
        centroid_method : str, optional
            '1d' or '2d' for centroid method. Defaults to 1d.
        """

        # Set vital connection parameters
            
        self.ip = ip
        self.max_step = max_step
        self.timeout = timeout
        self.home_reset = home_reset
        self.sleep_per_step = sleep_per_step 
        
        # If it's an Nth daisy chained controller, we want a 'N>' prefix before each message.
        # Otherwise, we want nothing.
        self.daisy = f'{daisy}>' if int(daisy) > 1 else ''
        
        # Initialize some command parameters
        self.cmd_dict = {'home_position': 'DH', 'exact_move': 'PA', 
                         'relative_move': 'PR', 'reset': 'RS',
                         'relative_move': 'PR', 'reset': 'RS',
                         'error_message': 'TB'}
        
        self.calibration = {} if calibration is None else calibration
        
        if centroid_method is None:
            self.centroid_method = centroid_1dg
        elif centroid_method == '1d':
            self.centroid_method = centroid_1dg
        elif centroid_method == '2d':
            self.centroid_method = centroid_2dg
        else:
            raise NotImplementedError('Only 1D an 2D centroiding is available.')


    def _open(self):
        """ Function to test a connection (ping the address and see if it
        sticks). """
        try:
            self.instrument_lib.urlopen(f'http://{self.ip}', timeout=self.timeout)
        except  Exception as e:
            raise OSError(f"The controller IP address : {self.ip} is not responding.") from e
            self.log.critical(f"The controller IP address : {self.ip} is not responding.")
            
        # Since there's no useful "object" to connect to here, instrument is
        # set to True to allow for open/close behavior 
        self.instrument = True
        self.log.info(f'IP address : {self.ip}, is online, and logging instantiated.')
        
        # Save current position as home.
        for axis in '1234':
            self.command('home_position', int(axis), 0)
            self.log.info('Current position saved as home.')
        
        return self.instrument

    def _close(self):
        """ Function for the close behavior. Return every parameter to zero
        and shut down the logging."""
        
        if self.home_reset:
            self.reset_controller()

    def reset_controller(self):
        """Function to reset the motors to where they started (or were last reset.)"""
        
        for axis in '1234':
            self.command('exact_move', int(axis), 0)
            self.command('home_position', int(axis), 0)
            self.log.info('Controller reset.')
        
    def absolute_move(self, axis, value):
        """ Function to make an absolute move.

        Parameters
        ----------
        axis : str
            Which axis to move. NOTE : in MotorController2
            class this is called "motor_id".
        value : int
            Number of steps. NOTE : in MotorController2
            class this is called "distance."
        """

        self.command('exact_move', axis, value)
            
    def relative_move(self, axis, value): 
        """ Function to make a relative move.

        Parameters
        ----------
        axis : str
            Which axis to move. NOTE : in MotorController2
            class this is called "motor_id".
        value : int
            Number of stpes. NOTE : in MotorController2
            class this is called "distance."
        """
        
        self.command('relative_move', axis, value)

    @http_except
    def command(self, cmd_key, axis, value):
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
        """
        
        set_message = self._build_message(cmd_key, 'set', axis, value)
        get_message = self._build_message(cmd_key, 'get', axis)
        
        initial_value = self._send_message(get_message, 'get') if cmd_key == 'relative_move' else 0
        
        self._send_message(set_message, 'set')
        
        # Calculate time move will take so we don't overlap messages
        # Keep in mind sometimes steps are negative
        # Default velocity is 2000 steps/second
        move_time = np.abs(value*self.sleep_per_step)
        catkit.util.sleep(move_time)
        
        set_value = float(self._send_message(get_message, 'get')) - float(initial_value)
        
        if float(set_value) != value:
            error_msg = f"Newport Pico Motor failed to move as {set_value} != {value}. Try increasing sleep duration."
            self.log.error(error_msg)
            raise RuntimeError(error_msg)
         
        self.log.info(f'Command sent. Action : {cmd_key}. Axis : {axis}. Value : {value}')

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

        x1, y1 = self.centroid_method(img_before)
        x2, y2 = self.centroid_method(img_after)

        x_move = x1 - x2
        y_move = y1 - y2
        
        r = np.sqrt(x_move**2 + y_move**2)
        theta = np.arctan(y_move/x_move)
        
        r_ratio = r/move
        
        if axis in [1,3]:
            delta_theta = theta - 0
        
        elif axis in [2, 4]:
            delta_theta = theta - np.pi/2
        
        else:
            raise NotImplementedError('Only axis 1 through 4 are defined.')
        
        self.calibration[f'r_ratio_{axis}'] = r_ratio
        self.calibration[f'delta_theta_{axis}'] = delta_theta
        
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
        for cmd_key in ('home_position', 'relative_move'):
            
            message = self._build_message(cmd_key, 'get', axis)
            value = self._send_message(message, 'get') 
            state_dict[f'{cmd_key}_{axis}'] = value
            self.log.info(f'For axis {axis}, {cmd_key} is set to {value}')
        
        return state_dict
        
    @http_except
    def reset(self):
        """Resets the controller."""
        
        message = self._build_message('reset', 'reset')
        self._send_message(message, 'set')
        self.log.info('Controller reset.')

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
            message = f'{self.daisy}{axis}{address}?'
        
        elif cmd_type == 'set': 
            if axis is None or not isinstance(axis, int):
                raise ValueError("This command requires an integer axis.")
            elif value is None or not isinstance(value, int):
                raise ValueError("This command requires an integer value.")
            elif cmd_key in ['exact_move', 'relative_move'] and np.abs(value) > self.max_step:
                raise ValueError(f'You can only move {self.max_step} in any direction.')
            else:
                message = f'{self.daisy}{axis}{address}{value}'
            
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
        with self.instrument_lib.urlopen(f'http://{self.ip}/cmd_send.cgi?{form_data}', timeout=self.timeout) as html:
            resp = str(html.read())
        
        if cmd_type == 'get':
            # Pull out the response from the html on the page 
            # The output will be nestled between --> and \\r
            response = resp.split('response')[1].split('-->')[1].split('\\r')[0]

            return response
