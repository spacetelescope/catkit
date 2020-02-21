"""Interface for IrisAO segmented deformable mirror controller."""

import collections
import datetime
import os
import time

import IrisAO_Python
import numpy as np

import catkit.util
from catkit.hardware import testbed_state
from catkit.interfaces.DeformableMirrorController import DeformableMirrorController
from catkit.hardware.iris_ao import util as iris_util
from catkit.hardware.iris_ao.segmented_dm_command import SegmentedDmCommand


class IrisAoDmController(DeformableMirrorController):

    instrument_lib = IrisAO_Python

    mirror_config_file_ext = ".mcf"
    driver_config_file_ext = ".dcf"

    def initialize(self,
                   mirror_serial,
                   driver_serial,
                   disable_hardware,
                   config_file_dir_path,
                   num_segments=iris_util.iris_num_segments()):
        """
        Initialize dm manufacturer specific object - this does not, nor should it, open a
        connection.
        """

        self.log.info("Opening IrisAO connection")
        # Create class attributes for storing an individual command.
        self.command = None

        self.mirror_serial = mirror_serial
        self.driver_serial = driver_serial
        self.disableHardware = disable_hardware
        self.num_segments = num_segments


        # Determine filename paths for calibration/config files.
        self.config_file_dir_path = os.path.abspath(config_file_dir_path)
        if not os.path.isdir(self.config_file_dir_path):
            raise FileNotFoundError(f"{self.config_id}: config_file_dir_path: '{self.config_file_dir_path}' not found.")
        self.mirror_config_file_path = os.path.join(self.config_file_dir_path, self.mirror_serial + self.mirror_config_file_ext)
        self.driver_config_file_path = os.path.join(self.config_file_dir_path, self.driver_serial + self.driver_config_file_ext)
        if not os.path.isFile(self.mirror_config_file_path):
            raise FileNotFoundError(f"{self.config_id}: '{self.mirror_config_file_path}' not found.")
        if not os.path.isFile(self.driver_config_file_path):
            raise FileNotFoundError(f"{self.config_id}: '{self.driver_config_file_path}' not found.")

        # The IrisAO driver expects the .dcf and .mcf config files in the working dir.
        # Neither adding them to PATH nor PYTHONPATH worked.
        # This is a workaround.
        # These files remain copied until their refs go out of scope, i.e., when this class instance drops out of scope.
        cwd = os.path.abspath(os.getcwd())
        self._mirror_config_file_copy = catkit.util.TempFileCopy(self.mirror_config_file_path, cwd)
        self._driver_config_file_copy = catkit.util.TempFileCopy(self.driver_config_file_path, cwd)

    def _send_data(self, data):
        """
        To send data to the IrisAO, you must write to the ConfigPTT.ini file
        to send the command

        :param data: dict, the command to be sent to the DM
        """

        if not self.instrument:
            raise Exception(f"{self.config_id}: Open connection required.")

        if not isinstance(data, dict):
            raise TypeError(f"{self.config_id}: expected 'data' to be a dict and not '{type(data)}'.")

        segments = list(data.keys())
        ptt = list(data.values())

        if len(segments) != len(ptt):
            raise TypeError(f"{self.config_id}: Corrupt data - each segment must have a corresponding PTT and vice versa.")

        try:
            self.instrument_lib._setPosition(self.instrument, segments, len(segments), ptt)
        except Exception as error:
            raise Exception(f"{self.config_id}: Failed to send command data to device.") from error

    def _open(self):
        """Open a connection to the IrisAO"""

        hardware_enabled = not self.disableHardware
        try:
            self.instrument = self.instrument_lib._connect(self.mirror_serial.encode(),
                                                           self.driver_serial.encode(),
                                                           hardware_enabled)
        except Exception as error:
            self.instrument = None  # Don't try closing
            raise Exception(f"{self.config_id}: Failed to connect to device.") from error

        # Initialize the Iris to zeros
        self.zero()

        return self.instrument

    def zero(self):
        """Put zeros on the DM"""

        self.apply_shape(SegmentedDmCommand(iris_util.create_zero_dictionary(self.num_segments), flat_map=False))

    def _close(self):
        """Close connection safely."""

        try:
            try:
                # Set IrisAO to zero
                self.zero()
            finally:
                self.instrument_lib._release(self.instrument)
        finally:
            self.instrument = None
            self._close_iris_controller_testbed_state()

    def get_position(self, segments=None):
        """ Read the PTT for the given segments from the device itself. """

        if not self.instrument:
            raise Exception(f"{self.config_id}: Open connection required.")

        segments = segments if segments else iris_util.iris_pupil_numbering(self.num_segments)

        # _getMirrorPosition() expects a list of segments
        if not isinstance(segments, collections.Iterable):
            segments = [segments]

        if isinstance(segments, np.ndarray):
            segments = segments.tolist()

        try:
            ptt, _locked, _reachable = self.instrument_lib._getMirrorPosition(self.instrument, segments, len(segments))
        except Exception as error:
            raise Exception(f"{self.config_id}: Failed to get command data from device.") from error

        if len(segments) != len(ptt):
            raise TypeError(f"{self.config_id}: Corrupt data - each segment must have a corresponding PTT and vice versa.")

        return SegmentedDmCommand(dict(zip(segments, ptt)), flat_map=False)

    def apply_shape(self, dm_shape, dm_num=1):
        """
        Apply a command object to the Iris AO after adding the flatmap from the configfile.
        The units of said SegmentedDmCommand object are mrad for tip/tilt, um for piston.

        :param dm_shape: instance of SegmentedDmCommand class
        :param dm_num: int, this must always be 1 since only one DM can be controlled
                       with this controller.
        """
        if dm_num != 1:
            raise NotImplementedError("You can only control one Iris AO at a time")

        if not isinstance(dm_shape, SegmentedDmCommand):
            raise TypeError(f"{self.config_id}: expected 'dm_shape' to be of type `{SegmentedDmCommand.__qualname__}' and not '{type(dm_shape)}'.")

        # Use DmCommand class to format the single command correctly.
        command_dict = dm_shape.to_command()

        # Send array to DM.
        self._send_data(command_dict)

        # Update the dm_command class attribute.
        # TODO: This should be stashing a SegmentedDmCommand object and not a naked dict.
        self.command = command_dict

        # Update the testbed_state.
        self._update_iris_state(dm_shape)

    def apply_shape_to_both(self, dm1_shape=None, dm2_shape=None):
        """ Method only used by the BostonDmController"""
        raise NotImplementedError("apply_shape_to_both is not implemented for the Iris AO")

    @staticmethod
    def _update_iris_state(command_object):
        testbed_state.iris_command_object = command_object

    @staticmethod
    def _close_iris_controller_testbed_state():
        testbed_state.iris_command_object = None
