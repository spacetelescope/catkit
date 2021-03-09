import os
import sys

import numpy as np

from catkit.interfaces.DeformableMirrorController import DeformableMirrorController
from catkit.hardware.boston.DmCommand import DmCommand


# BMC is Boston's library and it only works on windows.
try:
    sdk_path = os.environ.get('CATKIT_BOSTON_SDK_PATH')
    if sdk_path is not None:
        sys.path.append(sdk_path)
        import bmc
    else:
        bmc = None
except ImportError:
    bmc = None

"""Interface for Boston Micro-machines deformable mirror controller that can control 2 DMs.  
   It does so by interpreting the first half of the command for DM1, and the second for DM2.
   This controller cannot control the two DMs independently, it will always send a command to both."""


class BostonDmController(DeformableMirrorController):

    instrument_lib = bmc

    def _clear_state(self):
        self.dm1_command = None
        self.dm2_command = None
        self.dm1_command_object = None
        self.dm2_command_object = None

    def initialize(self, serial_number, command_length, dac_bit_width):
        """ Initialize dm manufacturer specific object - this does not, nor should it, open a connection."""
        self.log.info("Opening DM connection")
        # Create class attributes for storing individual DM commands.
        self._clear_state()
        self.serial_num = serial_number
        self.command_length = command_length
        self.dac_bit_width = dac_bit_width

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
        self._clear_state()
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
        try:
            self.send_data(zeros)  # TODO: call self.apply_shape_to_both()
        except Exception:
            self._clear_state()
            raise
        else:
            # Store the current dm_command values in class attributes.
            self.dm1_command = zeros
            self.dm2_command = zeros.copy()  # dm 1 & 2 should NOT be using the same memory
        self.dm_controller = self.instrument  # For legacy API purposes

        return self.instrument

    def _close(self):
        """Close dm connection safely."""
        try:
            try:
                self.log.info("Closing DM connection")

                # FIXME: I'm pretty sure the new SDK does this under the hood.
                # Set the DM to zeros.
                zeros = np.zeros(self.command_length, dtype=float)
                self.send_data(zeros)
            finally:
                self.instrument.close_dm()
        finally:
            self.instrument = None
            self._clear_state()

    def apply_shape_to_both(self, dm1_command_object, dm2_command_object,
                            flat_map=True,
                            bias=False,
                            as_voltage_percentage=False,
                            as_volts=False,
                            sin_specification=None):
        """Combines both commands and sends to the controller to produce a shape on each DM."""
        self.log.info("Applying shape to both DMs")

        if not isinstance(dm1_command_object, DmCommand):
            dm1_command_object = DmCommand(data=dm1_command_object,
                                           dm_num=1,
                                           flat_map=flat_map,
                                           bias=bias,
                                           as_voltage_percentage=as_voltage_percentage,
                                           as_volts=as_volts,
                                           sin_specification=sin_specification)

        if not isinstance(dm2_command_object, DmCommand):
            dm2_command_object = DmCommand(data=dm2_command_object,
                                           dm_num=2,
                                           flat_map=flat_map,
                                           bias=bias,
                                           as_voltage_percentage=as_voltage_percentage,
                                           as_volts=as_volts,
                                           sin_specification=sin_specification)

        # Ensure that the correct dm_num is set.
        dm1_command_object.dm_num = 1
        dm2_command_object.dm_num = 2

        # Use DmCommand class to format the commands correctly (with zeros for other DM).
        dm1_command = dm1_command_object.to_dm_command()
        dm2_command = dm2_command_object.to_dm_command()

        # Add both arrays together (first half and second half) and send to DM.
        full_command = dm1_command + dm2_command
        try:
            self.send_data(full_command)
        except Exception:
            # We shouldn't guarantee the state of the DM.
            self._clear_state()
            raise
        else:
            # Update both dm_command class attributes.
            self.dm1_command = dm1_command
            self.dm2_command = dm2_command
            self.dm1_command_object = dm1_command_object
            self.dm2_command_object = dm2_command_object

    def apply_shape(self, dm_command_object, dm_num,
                    flat_map=True,
                    bias=False,
                    as_voltage_percentage=False,
                    as_volts=False,
                    sin_specification=None):
        self.log.info("Applying shape to DM " + str(dm_num))
        """Forms a command for a single DM, and re-sends the existing shape to other DM."""

        if not isinstance(dm_command_object, DmCommand):
            dm_command_object = DmCommand(data=dm_command_object,
                                          dm_num=dm_num,
                                          flat_map=flat_map,
                                          bias=bias,
                                          as_voltage_percentage=as_voltage_percentage,
                                          as_volts=as_volts,
                                          sin_specification=sin_specification)


        # Ensure the dm_num is correct.
        dm_command_object.dm_num = dm_num

        # Use DmCommand class to format the single command correctly (with zeros for other DM).
        dm_command = dm_command_object.to_dm_command()

        # Grab the other DM's currently applied shape.
        other_dm_command = self.dm2_command if dm_num == 1 else self.dm1_command

        # Add both arrays together (first half and second half) and send to DM.
        full_command = dm_command + other_dm_command
        try:
            self.send_data(full_command)
        except Exception:
            # We shouldn't guarantee the state of the DM.
            self._clear_state()
            raise
        else:
            # Update the dm_command class attribute.
            if dm_num == 1:
                self.dm1_command = dm_command
                self.dm1_command_object = dm_command_object
            else:
                self.dm2_command = dm_command
                self.dm2_command_object = dm_command_object
