"""Interface for IrisAO segmented deformable mirror controller."""

import os
import subprocess

from catkit.hardware import testbed_state
from catkit.interfaces.DeformableMirrorController import DeformableMirrorController

from catkit.hardware.iris_ao import util


class IrisAoDmController(DeformableMirrorController):

    instrument_lib = subprocess

    def initialize(self, mirror_serial, driver_serial, disable_hardware, path_to_dm_exe,
                   filename_ptt_dm):
        """
        Initialize dm manufacturer specific object - this does not, nor should it, open a
        connection.
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
        """Put zeros on the DM.

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
        """ Method only used by the BostomDmController"""
        raise NotImplementedError("apply_shape_to_both is not implmented for the Iris AO")

    @staticmethod
    def _update_iris_state(command_object):
        testbed_state.iris_command_object = command_object

    @staticmethod
    def _close_iris_controller_testbed_state():
        testbed_state.iris_command_object = None
