from hicat.hardware import testbed_state
from catkit.interfaces.DeformableMirrorController import DeformableMirrorController
from hicat.config import CONFIG_INI
import numpy as np

# BMC is Boston's library and it only works on windows.
try:
    from catkit.hardware.boston.sdk.python3.v3_5_1 import bmc
except ImportError:
    bmc = None

"""Interface for Boston Micro-machines deformable mirror controller that can control 2 DMs.  
   It does so by interpreting the first half of the command for DM1, and the second for DM2.
   This controller cannot control the two DMs independently, it will always send a command to both."""


class BostonDmController(DeformableMirrorController):

    instrument_lib = bmc

    def initialize(self):
        """Opens connection with dm and returns the dm manufacturer specific object."""
        self.log.info("Opening DM connection")
        # Create class attributes for storing individual DM commands.
        self.dm1_command = None
        self.dm2_command = None
        self.command_length = CONFIG_INI.getint(self.config_id, "command_length")
        self.serial_num = CONFIG_INI.get(self.config_id, "serial_num")

    def send_data(self, data):

        # The DM controller expects the command to be unitless (normalized Volts): 0.0 - 1.0, where 1.0 := max_volts
        data_min = np.min(data)
        data_max = np.max(data)
        if data_min < 0 or data_max > 1:
            self.log.warning(f"DM command out of range and will be clipped by hardware. min:{data_min}, max:{data_max}")

        status = self.instrument.send_data(data)
        if status != self.instrument_lib.NO_ERR:
            raise Exception("{}: Failed to send data - {}".format(self.config_id,
                                                                  self.instrument.error_string(status)))

    def _open(self):
        dm = self.instrument_lib.BmcDm()
        status = dm.open_dm(self.serial_num)
        if status != self.instrument_lib.NO_ERR:
            raise Exception("{}: Failed to connect - {}.".format(self.config_id,
                                                                 dm.error_string(status)))

        # If we get this far, a connection has been successfully opened.
        # Set self.instrument so that we can close if anything here subsequently fails.
        self.instrument = dm
        hardware_command_length = dm.num_actuators()
        if self.command_length != hardware_command_length:
            raise ValueError("config.ini error - '{}':'command_length' = {} but hardware gives {}.".format(self.config_id,
                                                                                                           self.command_length,
                                                                                                           hardware_command_length))

        # Initialize the DM to zeros.
        zeros = np.zeros(self.command_length, dtype=float)
        self.send_data(zeros)

        # Store the current dm_command values in class attributes.
        self.dm1_command = zeros
        self.dm2_command = zeros[:]  # dm 1 & 2 should NOT be using the same memory
        self.dm_controller = self.instrument  # For legacy API purposes

        return self.instrument

    def close(self):
        """Close dm connection safely."""
        try:
            self.log.info("Closing DM connection")

            # FIXME: I'm pretty sure the new SDK does this under the hood.
            # Set the DM to zeros.
            zeros = np.zeros(self.command_length, dtype=float)
            self.send_data(zeros)
        finally:
            self.instrument.close_dm()
            self.instrument = None

        # Update testbed_state.
        self.__close_dm_controller_testbed_state()

    def apply_shape_to_both(self, dm1_command_object, dm2_command_object):
        """Combines both commands and sends to the controller to produce a shape on each DM."""
        self.log.info("Applying shape to both DMs")

        # Ensure that the correct dm_num is set.
        dm1_command_object.dm_num = 1
        dm2_command_object.dm_num = 2

        # Use DmCommand class to format the commands correctly (with zeros for other DM).
        dm1_command = dm1_command_object.to_dm_command()
        dm2_command = dm2_command_object.to_dm_command()

        # Add both arrays together (first half and second half) and send to DM.
        full_command = dm1_command + dm2_command
        self.send_data(full_command)

        # Update both dm_command class attributes.
        self.dm1_command = dm1_command
        self.dm2_command = dm2_command

        # Update testbed_state.
        self.__update_dm_state(dm1_command_object)
        self.__update_dm_state(dm2_command_object)

    def apply_shape(self, dm_command_object, dm_num):
        self.log.info("Applying shape to DM " + str(dm_num))
        """Forms a command for a single DM, and re-sends the existing shape to other DM."""

        # Ensure the dm_num is correct.
        dm_command_object.dm_num = dm_num

        # Use DmCommand class to format the single command correctly (with zeros for other DM).
        dm_command = dm_command_object.to_dm_command()

        # Grab the other DM's currently applied shape.
        other_dm_command = self.dm2_command if dm_num == 1 else self.dm1_command

        # Add both arrays together (first half and second half) and send to DM.
        full_command = dm_command + other_dm_command
        self.send_data(full_command)

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
            testbed_state.dm1_command_object = dm_command_object
        if dm_command_object.dm_num == 2:
            testbed_state.dm2_command_object = dm_command_object

    @staticmethod
    def __close_dm_controller_testbed_state():
        testbed_state.dm1_command_object = None
        testbed_state.dm2_command_object = None
