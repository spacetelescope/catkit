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
from abc import ABC, abstractmethod
import os

import numpy as np

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


class Controller(ABC):
    """ Abstract base class for all of the controllers."""

    def __init__(self):
        """ Initial function to set up logging and 
        set up the controller."""

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
        
        self.open_connection()
        self.define_status_keys()

    def __enter__(self):
        """ Enter function to allow context management."""

        return self

    def __exit__(self):
        """ Exit function to return all settings to base."""
        
        self.close_connection()
        self.logger.info('Everything has been reset. Enjoy your new life.')
    
    @abstractmethod
    def build_message(self, cmd_key, cmd_type, axis):
        """ Builds message for the controller."""

    @abstractmethod
    def check_response(self, response, axis, key, value):
        """ Checks the response matches the expected value."""
    
    @abstractmethod
    def close_connection(self):
        """Abstract method for the close behavior for whatever controller."""
    
    @abstractmethod
    def controller_except(self, function):
        """Abstract method to catch whatever error is thrown by the controller.
        Ex, for the tip/tilt it catches the USBErrors, for Newport it catches 
        HTTPErrors."""
    
    @abstractmethod
    def define_status_keys(self):
        """ Sets the keys to be returned with the ``get_status`` function."""

    @abstractmethod
    def open_connection(self):
        """ Opens controller connection. """

    @abstractmethod
    def send_message(self, message, cmd_type):
        """ Sends message to the controller."""

    @controller_except
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
        for cmd_key in self.status_keys:
            message = self.build_message(self, cmd_key, 'get', axis)
            value = self.send_message(message, 'get') 
            state_dict['{}_{}'.format(cmd_key, axis)] = value
            logging.info('For axis/channel {}, {} is set to {}'.format(axis, cmd_key, value))
        
        return state_dict
    
    @controller_except
    def command(self, cmd_key, axis, value):

        set_message = self.build_message(self, cmd_key, 'set', axis, value)
        get_message = self.build_message(self, cmd_key, 'get', axis)
        
        self.send_message(set_message, 'set')
        set_value = self.send_message(get_message, 'get')
        self.check_response(set_value, axis, cmd_key, value)
        
