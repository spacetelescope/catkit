from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
from abc import ABCMeta, abstractmethod

"""Interface for backup power supply (ex: UPS)"""


class BackupPower(object):
    __metaclass__ = ABCMeta

    def __init__(self, config_id, *args, **kwargs):
        self.config_id = config_id

    # Abstract Methods.
    @abstractmethod
    def get_status(self):
        """Queries backup power and reports status. Returns whatever format the device uses."""

    @abstractmethod
    def is_power_ok(self):
        """Boolean function to determine whether the system should initiate a shutdown."""
