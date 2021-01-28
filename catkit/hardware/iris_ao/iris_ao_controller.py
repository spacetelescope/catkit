"""Interface for IrisAO segmented deformable mirror controller."""

import os
import time

import IrisAO_Python

from catkit.interfaces.DeformableMirrorController import DeformableMirrorController
from catkit.hardware.iris_ao.segmented_dm_command import SegmentedDmCommand
from catkit.hardware.iris_ao import util


class IrisAoDmController(DeformableMirrorController):
    """ Device class to control the IrisAO DM. """

    instrument_lib = IrisAO_Python

    def initialize(self,
                   mirror_serial,
                   driver_serial,
                   mcf_filepath,
                   dcf_filepath,
                   disable_hardware=False):
        """
        Initialize dm manufacturer specific object - this does not, nor should it, open a
        connection.

        :param mirror_serial: string, The mirror serial number. This corresponds to a .mcf file that MUST include the
                              driver serial number under "Smart Driver". See README.
        :param driver_serial: string, The driver serial number. This corresponds to a .dcf file. See README.
        :param disable_hardware: bool, False := use hardware, True := all hardware APIs are NOOPs.
        :param mcf_filepath: string, Full path to .mcf file.
        :param dcf_filepath: string, Full path to .dcf file.
        """

        self.log.info("Opening IrisAO connection")
        # Create class attributes for storing an individual command.
        self.command_object = None
        self.mirror_serial = mirror_serial
        self.driver_serial = driver_serial
        self.disable_hardware = disable_hardware
        self.mcf_filepath = mcf_filepath
        self.dcf_filepath = dcf_filepath

        # Check config files exist.
        self.validate_config_files()

        # The IrisAO driver expects the .dcf and .mcf config files in the working dir.
        # Neither adding them to PATH nor PYTHONPATH worked.
        # This is a workaround.
        # These files remain copied until their refs go out of scope, i.e., when this class instance drops out of scope.
        cwd = os.path.abspath(os.getcwd())
        self._mirror_config_file_copy = catkit.util.TempFileCopy(self.mcf_filepath, cwd)
        self._driver_config_file_copy = catkit.util.TempFileCopy(self.dcf_filepath, cwd)

    @staticmethod
    def search_file(filepath, search_str, raise_exception=True):
        with open(filepath, 'r') as open_file:
            valid = False
            while True:
                line = open_file.readline()
                if not line:  # EOF
                    break
                if search_str in line:
                    valid = True
                    break
        if raise_exception:
            if not valid:
                raise ValueError(f"Couldn't find '{search_str}' in '{filepath}'.")
        return valid

    def validate_config_files(self):
        """ Check config files are correct for given serial numbers. """

        # Check files exist.
        if not os.path.isFile(self.mirror_config_file_path):
            raise FileNotFoundError(f"{self.config_id}: '{self.mirror_config_file_path}' not found.")
        if not os.path.isFile(self.driver_config_file_path):
            raise FileNotFoundError(f"{self.config_id}: '{self.driver_config_file_path}' not found.")

        # Check correct SN# are baked into filenames.
        if self.mirror_serial not in self.mcf_filepath:
            raise ValueError(f"The mirror SN# '{self.mirror_serial}' doesn't match that of the .mcf file '{self.mcf_filepath}'.")
        if self.driver_serial not in self.dcf_filepath:
            raise ValueError(f"The driver SN# '{self.driver_serial}' doesn't match that of the .dcf file '{self.dcf_filepath}'.")

        # Check SN# are fields within the files themselves. Only works for driver SN#.
        self.search_file(filepath=self.dcf_filepath, search_str=f"[SN:{self.driver_serial}]")
        self.search_file(filepath=self.mcf_filepath, search_str=f"// Smart Driver: {self.driver_serial}")

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
        hardware_enabled = not self.disable_hardware
        try:
            self.instrument = self.instrument_lib._connect(self.mirror_serial.encode(),
                                                           self.driver_serial.encode(),
                                                           hardware_enabled)
        except Exception as error:
            self.instrument = None  # Don't try closing
            raise Exception(f"{self.config_id}: Failed to connect to device.") from error

        # Initialize the Iris to zeros.
        self.zero()

        return self.instrument

    def zero(self, return_zeros=False):
        """Put zeros on the DM. This does not correspond to a flattened DM.

        :return: If return_zeros=True, return a dictionary of zeros
        """
        zero_list = util.create_zero_list(util.iris_num_segments(self.config_id))
        dm_shape = SegmentedDmCommand(dm_config_id=self.config_id)
        dm_shape.read_initial_command(zero_list)
        self.apply_shape(dm_shape)

        if return_zeros:
            return util.create_dict_from_list(zero_list, util.iris_pupil_naming(self.config_id))

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
        self.command_object = dm_shape

    def apply_shape_to_both(self, dm1_shape=None, dm2_shape=None):
        """Method only used by the BostonDmController"""
        raise NotImplementedError("apply_shape_to_both is not implemented for the Iris AO")

    @property
    def command(self):
        return self.command_object.to_command() if self.command_object is not None else None
