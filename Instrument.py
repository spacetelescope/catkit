from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
from abc import ABCMeta, abstractmethod
import logging


class Instrument(object, metaclass=ABCMeta):
    """Generic interface to any instrument, implements a context manager."""
    log = logging.getLogger(__name__)

    def __new__(cls, config_id):
        return super(Instrument, cls).__new__(cls)

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with the Instrument and sets class attributes for 'config_id'"""

        self.config_id = config_id
        self.socket_id = None
        self.instrument = self.initialize(*args, **kwargs)
        self.log.info("Initialized " + config_id)

    # Context manager Enter function, gets called automatically when the "with" statement is used.
    def __enter__(self, *args, **kwargs):
        return self

    # Context manager Exit function, gets called automatically the code exits the context of the "with" statement.
    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()
        self.instrument = None
        self.log.info("Safely closed connection to " + self.config_id)

    @abstractmethod
    def initialize(self, *args, **kwargs):
        """Implement this function to return an object that can control the instrument."""

    @abstractmethod
    def close(self):
        """Close connection safely."""
