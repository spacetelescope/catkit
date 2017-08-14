from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
from abc import *

"""Interface for backup power supply (ex: UPS)"""


class BackupPower(object):
    __metaclass__ = ABCMeta

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with the motor controller and sets class attributes for 'config_id' and 'motor'."""
        self.config_id = config_id

    # Abstract Methods.
    @abstractmethod
    def get_status(self):
        """Queries backup power and reports status. Returns whatever format the device uses."""

    @abstractmethod
    def is_shutdown_needed(self):
        """Boolean function to determine whether the system should initiate a shutdown."""
