"""Interface for IrisAO segmented deformable mirror controller."""

import ctypes
import os

from catkit.interfaces.DeformableMirrorController import DeformableMirrorController
from catkit.hardware.iris_ao.segmented_dm_command import SegmentedDmCommand
from catkit.hardware.iris_ao import util
import catkit.util


class IrisAOCLib:
    def __init__(self, dll_filepath):
        self.dll_filepath = dll_filepath
        self.dll = None

        if not self.dll:
            try:
                self.dll = ctypes.cdll.LoadLibrary(self.dll_filepath)
            except Exception as error:
                raise ImportError(f"Failed to load library '{self.dll_filepath}'.") from error

        # Declare prototypes.
        # void MirrorCommand (void* mirror, void* command);
        self._MirrorCommand = self.dll.MirrorCommand
        self._MirrorCommand.restype = None
        self._MirrorCommand.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        # void* MirrorConnect (char* mirror_serial, char* driver_serial, bool disabled);
        self._MirrorConnect = self.dll.MirrorConnect
        self._MirrorConnect.restype = ctypes.c_void_p
        self._MirrorConnect.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_bool]

        # void* MirrorRelease (void* mirror);
        self._MirrorRelease = self.dll.MirrorRelease
        self._MirrorRelease.restype = ctypes.c_void_p
        self._MirrorRelease.argtypes = [ctypes.c_void_p]

        # void SetMirrorPosition (void* mirror, unsigned int segment, float z, float xgrad, float ygrad);
        self._SetMirrorPosition = self.dll.SetMirrorPosition
        self._SetMirrorPosition.restype = None
        self._SetMirrorPosition.argtypes = [ctypes.c_char_p, ctypes.c_uint, ctypes.c_float, ctypes.c_float, ctypes.c_float]

    def MirrorCommand(self, mirror, command=None):
        if command is None:
            command = self.instrument_lib.MirrorSendSettings
        return self._MirrorConnect(mirror, command)

    def MirrorConnect(self, mirror_serial, driver_serial, disabled):
        return self._MirrorConnect(mirror_serial, driver_serial, disabled)

    def MirrorRelease(self, mirror):
        return self._MirrorRelease(mirror)

    def SetMirrorPosition(self, mirror, segment, z, xgrad, ygrad):
        return self._SetMirrorPosition(mirror, segment, z, xgrad, ygrad)


class IrisAoDmController(DeformableMirrorController):
    """ Device class to control the IrisAO DM. """

    instrument_lib = IrisAOCLib

    def initialize(self,
                   mirror_serial,
                   driver_serial,
                   mcf_filepath,
                   dcf_filepath,
                   dll_filepath,
                   disable_hardware=False):
        """
        Initialize dm manufacturer specific object - this does not, nor should it, open a
        connection.

        :param mirror_serial: string, The mirror serial number. This corresponds to a .mcf file that MUST include the
                              driver serial number under "Smart Driver". See README.
        :param driver_serial: string, The driver serial number. This corresponds to a .dcf file. See README.
        :param mcf_filepath: string, Full path to .mcf file.
        :param dcf_filepath: string, Full path to .dcf file.
        :param dll_filepath: string, Full path to IrisAO.Devices.dll (x64).
        :param disable_hardware: bool, False := use hardware, True := all hardware APIs are NOOPs.
        """

        self.dll_filepath = dll_filepath
        self.instrument_lib = self.instrument_lib(self.dll_filepath)

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
        To send data to the IrisAO.

        :param data: dict, the command to be sent to the DM
        """
        if not self.instrument:
            raise Exception(f"{self.config_id}: Open connection required.")

        if not isinstance(data, dict):
            raise TypeError(f"{self.config_id}: expected 'data' to be a dict and not '{type(data)}'.")

        try:
            for segment, ptt in data.items():
                # Pass values to connection handle (but not to driver box).
                self.instrument_lib.SetMirrorPosition(self.instrument, segment, ptt[0], ptt[1], ptt[2])
            # Now send the data to driver box.
            self.instrument_lib.MirrorCommand(self.instrument)
        except Exception as error:
            raise Exception(f"{self.config_id}: Failed to send command data to device.") from error

    def _open(self):
        """Open a connection to the IrisAO"""
        try:
            self.instrument = self.instrument_lib.MirrorConnect(self.mirror_serial.encode(),
                                                                self.driver_serial.encode(),
                                                                self.disable_hardware)
        except Exception as error:
            self.instrument = None  # Don't try closing
            raise Exception(f"{self.config_id}: Failed to connect to device.") from error

        # Initialize the Iris to zeros.
        self.instrument_lib.MirrorCommand(self.instrument, command=self.instrument_lib.MirrorInitSettings)

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
        self.instrument_lib.MirrorRelease(self.instrument)

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
