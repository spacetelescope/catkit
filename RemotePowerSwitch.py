from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
from abc import ABC, abstractmethod

"""Interface for remote controlled power switch."""


class RemotePowerSwitch(ABC):
    def __init__(self, config_id, *args, **kwargs):
        self.config_id = config_id

    # Abstract Methods.
    @abstractmethod
    def turn_on(self, outlet_id):
        """
        Turn on an individual outlet.
        """

    @abstractmethod
    def turn_off(self, outlet_id):
        """
        Turn off an individual outlet.
        """

    @abstractmethod
    def all_on(self):
        """
        Turn on all outlets.
        """

    @abstractmethod
    def all_off(self):
        """
        Turn off all outlets.
        """
