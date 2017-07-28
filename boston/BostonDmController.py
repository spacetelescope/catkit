from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from hicat.hardware import testbed_state
from hicat.interfaces.DeformableMirrorController import DeformableMirrorController
from .sdk import bmc
from hicat.config import CONFIG_INI
import numpy as np

"""Interface for Boston Micro-machines deformable mirror controller that can control 2 DMs.  
   It does so by interpreting the first half of the command for DM1, and the second for DM2.
   This controller cannot control the two DMs independently, it will always send a command to both."""


class BostonDmController(DeformableMirrorController):
    def initialize(self, *args, **kwargs):
        """Opens connection with dm and returns the dm manufacturer specific object."""

        # Connect to DM.
        dm = bmc.BmcDm()
        serial_num = CONFIG_INI.get(self.config_id, "serial_num")
        dm.open_dm(bytes(serial_num))
        command_length = dm.num_actuators()

        if command_length == 0:
            raise Exception("Unable to connect to " + self.config_id + ", make sure it is turned on.")

        # Initialize the DM to zeros.
        zeros = np.zeros(command_length, dtype=float)
        dm.send_data(zeros)

        # Store the current dm_command values in class attributes.
        self.dm1_command = zeros
        self.dm2_command = zeros
        return dm

    def close(self):
        """Close dm connection safely."""
        command_length = self.dm_controller.num_actuators()

        # Set the DM to zeros.
        zeros = np.zeros(command_length, dtype=float)
        self.dm_controller.send_data(zeros)
        self.dm_controller.close_dm()

        # Update testbed_state.
        self.__close_dm_controller_testbed_state()

    def apply_shape_to_both(self, dm1_command_object, dm2_command_object):
        """Combines both commands and sends to the controller to produce a shape on each DM."""

        # Ensure that the correct dm_num is set.
        dm1_command_object.dm_num = 1
        dm2_command_object.dm_num = 2

        # Use DmCommand class to format the commands correctly (with zeros for other DM).
        dm1_command = dm1_command_object.to_dm_command()
        dm2_command = dm2_command_object.to_dm_command()

        # Add both arrays together (first half and second half) and send to DM.
        full_command = dm1_command + dm2_command
        self.dm_controller.send_data(full_command)

        # Update both dm_command class attributes.
        self.dm1_command = dm1_command
        self.dm2_command = dm2_command

        # Update testbed_state.
        self.__update_dm_state(dm1_command_object)
        self.__update_dm_state(dm2_command_object)

    def apply_shape(self, dm_command_object, dm_num):
        """Forms a command for a single DM, and re-sends the existing shape to other DM."""

        # Ensure the dm_num is correct.
        dm_command_object.dm_num = dm_num

        # Use DmCommand class to format the single command correctly (with zeros for other DM).
        dm_command = dm_command_object.to_dm_command()

        # Grab the other DM's currently applied shape.
        other_dm_command = self.dm2_command if dm_num == 1 else self.dm1_command

        # Add both arrays together (first half and second half) and send to DM.
        full_command = dm_command + other_dm_command
        self.dm_controller.send_data(full_command)

        # Update the dm_command class attribute.
        if dm_num == 1:
            self.dm1_command = dm_command
        else:
            self.dm2_command = dm_command

        # Update the testbed_state.
        self.__update_dm_state(dm_command_object)

    @staticmethod
    def __update_dm_state(dm_command_object):
        if dm_command_object.dm_num == 1:
            testbed_state.bias_dm1 = dm_command_object.bias
            testbed_state.flat_map_dm1 = dm_command_object.flat_map
            testbed_state.sine_wave_specifications_dm1 = dm_command_object.sin_specification
        if dm_command_object.dm_num == 2:
            testbed_state.bias_dm2 = dm_command_object.bias
            testbed_state.flat_map_dm2 = dm_command_object.flat_map
            testbed_state.sine_wave_specifications_dm2 = dm_command_object.sin_specification

    @staticmethod
    def __close_dm_controller_testbed_state():
        testbed_state.sine_wave_specifications_dm1 = []
        testbed_state.bias_dm1 = False
        testbed_state.flat_map_dm1 = False
        testbed_state.sine_wave_specifications_dm2 = []
        testbed_state.bias_dm2 = False
        testbed_state.flat_map_dm2 = False
