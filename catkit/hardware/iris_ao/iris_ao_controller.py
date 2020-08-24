"""Interface for IrisAO segmented deformable mirror controller."""

import os
import subprocess

from catkit.hardware import testbed_state
from catkit.interfaces.DeformableMirrorController import DeformableMirrorController

from catkit.hardware.iris_ao import util


class IrisAoDmController(DeformableMirrorController):
    """
    The low-level IrisAO API is written in C, and this class bridges to the compiled executable 'DM_Control.exe' stored
    locally on the machine that controls the IrisAO mirror. The basic functionality is that the user creates a command
    and stores it to an ini file called 'ConfigPTT.ini'. The executable then grabs that ini file and applies the piston,
    tip, tilt (PTT) values in that file to the hardware.

    The executable 'DM_Control.exe' is controlled by passing strings to it with stdin. E.g.:

    dm.stdin.write('config\n')
    dm.stdin.flush()

    will load the PTT values in the file specified with the variable filename_ptt_dm.

    Further details can be found in the linked PDF in this comment on GitHub:
    https://github.com/spacetelescope/instrument-interface-library/pull/71#discussion_r466536405
    """

    instrument_lib = subprocess

    def initialize(self, mirror_serial, driver_serial, disable_hardware, path_to_dm_exe,
                   filename_ptt_dm):
        """
        Initialize dm manufacturer specific object - this does not, nor should it, open a
        connection.

        :param mirror_serial: string, The mirror serial number. This corresponds to a .mcf file that MUST include the
                              driver serial number under "Smart Driver". See README.
        :param driver_serial: string, The driver serial number. This corresponds to a .dcf file. See README.
        :param disable_hardware: bool, If False, will run on hardware (always used on JOST this way). If True,
                                 probably (!) just runs the GUI? We never used it with True, so not sure.
        :param path_to_dm_exe: string, The path to the local directory that houses the DM_Control.exe file.
        :param filename_ptt_dm: string, Full path including filename of the ini file that provides the PTT values to be
                                loaded onto the hardware, e.g. ".../ConfigPTT.ini".
        """

        self.log.info("Opening IrisAO connection")
        # Create class attributes for storing an individual command.
        self.command = None

        self.mirror_serial = mirror_serial
        self.driver_serial = driver_serial

        # For the suprocess call
        self.disable_hardware = disable_hardware
        self.path_to_dm_exe = path_to_dm_exe
        self.full_path_dm_exe = os.path.join(path_to_dm_exe, 'DM_Control.exe')

        # Where to write ConfigPTT.ini file that gets read by the C++ code
        self.filename_ptt_dm = filename_ptt_dm

    def send_data(self, data):
        """
        To send data to the IrisAO, you must write to the ConfigPTT.ini file
        to send the command

        :param data: dict, the command to be sent to the DM
        """
        # Write to ConfigPTT.ini
        self.log.info("Creating config file: %s", self.filename_ptt_dm)
        util.write_ini(data, path=self.filename_ptt_dm, mirror_serial=self.mirror_serial,
                       driver_serial=self.driver_serial)

        # Apply the written .ini file to DM
        self.instrument.stdin.write(b'config\n')
        self.instrument.stdin.flush()

    def _open(self):
        """Open a connection to the IrisAO"""
        self.instrument = self.instrument_lib.Popen([self.full_path_dm_exe, self.disable_hardware],
                                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                    stderr=subprocess.PIPE,
                                                    cwd=self.path_to_dm_exe, bufsize=1)
        # Initialize the Iris to zeros.
        zeros = self.zero(return_zeros=True)

        # Store the current dm_command values in class attributes.
        self.command = zeros
        self._update_iris_state(self.command)

        return self.instrument

    def zero(self, return_zeros=False):
        """Put zeros on the DM. This does not in general correspond to a flattened DM.

        :return: If return_zeros=True, return a dictionary of zeros
        """
        zero_list = util.create_zero_list(util.iris_num_segments())
        zeros = util.create_dict_from_list(zero_list, util.iris_pupil_naming())
        self.send_data(zeros)

        # Update the testbed state
        self._update_iris_state(zeros)

        if return_zeros:
            return zeros

    def _close(self):
        """Close connection safely."""
        try:
            self.log.info('Closing Iris AO.')
            # Set IrisAO to zero
            self.zero()
            self.instrument.stdin.write(b'quit\n')
            self.instrument.stdin.close()
        finally:
            self.instrument = None
            self._close_iris_controller_testbed_state()

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

        # Use DmCommand class to format the single command correctly.
        command = dm_shape.to_command()

        # Send array to DM.
        self.send_data(command)

        # Update the dm_command class attribute.
        self.command = command

        # Update the testbed_state.
        self._update_iris_state(dm_shape)

    def apply_shape_to_both(self, dm1_shape=None, dm2_shape=None):
        """Method only used by the BostonDmController"""
        raise NotImplementedError("apply_shape_to_both is not implemented for the Iris AO")

    @staticmethod
    def _update_iris_state(command_object):
        testbed_state.iris_command_object = command_object

    @staticmethod
    def _close_iris_controller_testbed_state():
        testbed_state.iris_command_object = None
