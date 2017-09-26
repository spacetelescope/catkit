from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from abc import ABCMeta, abstractmethod

"""Interface for a deformable mirror controller that can control 2 DMs.  
   It does so by interpreting the first half of the command for DM1, and the second for DM2.
   This controller cannot control the two DMs independently, it will always send a command to both."""


class DeformableMirrorController(object):
    __metaclass__ = ABCMeta

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with the DM and sets class attributes for 'config_id' and 'dm'."""
        self.config_id = config_id

        # Create class attributes for storing individual DM commands.
        self.dm1_command = None
        self.dm2_command = None
        self.dm_controller = self.initialize(self, *args, **kwargs)
        print("Opened connection to DM " + config_id)

    # Implementing context manager.
    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()
        self.dm_controller = None
        print("Safely closed DM " + self.config_id)

    # Abstract Methods.
    @abstractmethod
    def initialize(self, *args, **kwargs):
        """Opens connection with dm and returns the dm manufacturer specific object."""

    @abstractmethod
    def close(self):
        """Close dm connection safely."""

    @abstractmethod
    def apply_shape_to_both(self, dm1_shape, dm2_shape):
        """Combines both commands and sends to the controller to produce a shape on each DM."""

    @abstractmethod
    def apply_shape(self, dm_shape, dm_num):
        """Forms a command for a single DM, with zeros padded for the DM not in use."""
