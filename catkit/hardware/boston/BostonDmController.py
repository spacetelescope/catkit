import os
import sys
import threading

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

        self.channels = {}
        self.lock = threading.Lock()

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

    def apply_shape_to_both(self, dm1_shape, dm2_shape,
                            flat_map=True,
                            bias=False,
                            as_voltage_percentage=False,
                            as_volts=False,
                            sin_specification=None,
                            output_path=None,
                            channel=None):
        """ Combines both commands and sends to the controller to produce a shape on each DM.
        :param dm<1|2>_shape: catkit.hardware.boston.DmCommand.DmCommand or numpy array of the following shapes: 34x34, 1x952,
                         1x2048, 1x4096. Interpreted by default as the desired DM surface height in units of meters, but
                         see parameters as_volts and as_voltage_percentage.
        :param flat_map: If true, add flat map correction to the data before outputting commands
        :param bias: If true, add bias to the data before outputting commands
        :param as_voltage_percentage: Interpret the data as a voltage percentage instead of meters; Deprecated.
        :param as_volts: If true, interpret the data as volts instead of meters
        :param sin_specification: Add this sine to the data
        :param output_path: str, Path to save commands to if provided. Default `None` := don't save.
        :param channel: str or None, the DM channel on which to write this shape. Default `None` := set the entire shape.
        """
        self.log.info("Applying shape to both DMs")

        with self.lock:
            if channel is not None:
                if isinstance(dm1_shape, DmCommand) or isinstance(dm2_shape, DmCommand):
                    raise ValueError('DM shapes cannot be DmCommands when using channels.')

                self.channels[channel] = (dm1_shape, dm2_shape)

                dm1_shape = 0
                dm2_shape = 0

                for dm1, dm2 in self.channels.values():
                    dm1_shape += dm1
                    dm2_shape += dm2

            if not isinstance(dm1_shape, DmCommand):
                dm1_shape = DmCommand(data=dm1_shape,
                                    dm_num=1,
                                    flat_map=flat_map,
                                    bias=bias,
                                    as_voltage_percentage=as_voltage_percentage,
                                    as_volts=as_volts,
                                    sin_specification=sin_specification)

            if not isinstance(dm2_shape, DmCommand):
                dm2_shape = DmCommand(data=dm2_shape,
                                    dm_num=2,
                                    flat_map=flat_map,
                                    bias=bias,
                                    as_voltage_percentage=as_voltage_percentage,
                                    as_volts=as_volts,
                                    sin_specification=sin_specification)

            # Ensure that the correct dm_num is set.
            dm1_shape.dm_num = 1
            dm2_shape.dm_num = 2

            if output_path is not None:
                dm1_shape.export_fits(output_path)
                dm2_shape.export_fits(output_path)

            # Use DmCommand class to format the commands correctly (with zeros for other DM).
            dm1_command = dm1_shape.to_dm_command()
            dm2_command = dm2_shape.to_dm_command()

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
                self.dm1_command_object = dm1_shape
                self.dm2_command_object = dm2_shape

    def apply_shape(self, dm_shape, dm_num,
                    flat_map=True,
                    bias=False,
                    as_voltage_percentage=False,
                    as_volts=False,
                    sin_specification=None,
                    output_path=None):
        """ Forms a command for a single DM, and re-sends the existing shape to other DM.
        :param dm_shape: catkit.hardware.boston.DmCommand.DmCommand or numpy array of the following shapes: 34x34, 1x952,
                     1x2048, 1x4096. Interpreted by default as the desired DM surface height in units of meters, but
                     see parameters as_volts and as_voltage_percentage.
        :param dm_num: Which DM to apply the shape to. Valid values are 1, 2.
        :param flat_map: If true, add flat map correction to the data before outputting commands
        :param bias: If true, add bias to the data before outputting commands
        :param as_voltage_percentage: Interpret the data as a voltage percentage instead of meters; Deprecated.
        :param as_volts: If true, interpret the data as volts instead of meters
        :param sin_specification: Add this sine to the data
        :param output_path: str, Path to save commands to if provided. Default `None` := don't save.
        """
        self.log.info("Applying shape to DM " + str(dm_num))

        if not isinstance(dm_shape, DmCommand):
            dm_shape = DmCommand(data=dm_shape,
                                 dm_num=dm_num,
                                 flat_map=flat_map,
                                 bias=bias,
                                 as_voltage_percentage=as_voltage_percentage,
                                 as_volts=as_volts,
                                 sin_specification=sin_specification)


        # Ensure the dm_num is correct.
        dm_shape.dm_num = dm_num

        if output_path is not None:
            dm_shape.export_fits(output_path)
            other_dm_command_object = self.dm2_command_object if dm_num == 1 else self.dm1_command_object
            other_dm_command_object.export_fits(output_path)

        # Use DmCommand class to format the single command correctly (with zeros for other DM).
        dm_command = dm_shape.to_dm_command()

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
                self.dm1_command_object = dm_shape
            else:
                self.dm2_command = dm_command
                self.dm2_command_object = dm_shape
