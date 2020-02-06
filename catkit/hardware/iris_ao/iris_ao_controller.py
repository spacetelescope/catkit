"""Interface for IrisAO segmented deformable mirror controller."""

import logging
import os
import subprocess

import numpy as np

from catkit.hardware import testbed_state
from catkit.interfaces.DeformableMirrorController import DeformableMirrorController

from catkit.config import CONFIG_INI
from catkit.hardware.iris_ao import util


class IrisAoController(DeformableMirrorController):

    log = logging.getLogger(__name__)

    #instrument_lib = iao #TODO: what I import for irisAO software - if anything

    def initialize(self, mirror_serial, driver_serial, disable_hardware, path_to_dm_exe,
                   filename_ptt_dm):
        """ Initialize dm manufacturer specific object - this does not, nor should it, open a connection."""
        self.log.info("Opening IrisAO connection")
        # Create class attributes for storing an individual command.
        self.command = None

        self.mirror_serial = mirror_serial
        self.driver_serial = driver_serial

        # For the suprocess call
        self.disableHardware = disable_hardware
        self.path_to_dm_exe = path_to_dm_exe
        self.full_path_dm_exe = os.path.join(path_to_dm_exe, 'DM_Control.exe')

        # Where to write ConfigPTT.ini file that gets read by the C++ code
        self.filename_ptt_dm = filename_ptt_dm

        self.dm = None


    def send_data(self, data):
        """ To send data to the IrisAO, you must write to the ConfigPTT.ini file
        and then use stdin.write(b'config\n') and stdin.flush() to send the command
        """
        # Write to ConfigPTT.ini
        util.write_ini(data, path=self.filename_ptt_dm, mirror_serial=self.mirror_serial,
                       driver_serial=self.driver_serial)

        # Apply the written .ini file to DM
        self.dm.stdin.write(b'config\n')
        self.dm.stdin.flush()


    def _open(self):
        """
        Open a connection to the IrisAO
        """
        self.dm = subprocess.Popen([self.full_path_dm_exe, self.disableHardware],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   cwd=self.path_to_dm_exe, bufsize=1)
        # Initialize the Iris to zeros.
        zeros = self._zero(return_zeros=True)

        # Store the current dm_command values in class attributes.
        self.command = zeros
        self.__update_iris_state(self.command)


    def _zero(self, return_zeros=False):
        """Zero out DM"""
        array = np.zeros((util.IRIS_NUM_SEGMENTS), dtype=(float, 3))
        zeros = util.create_dict_from_array(array)
        self.send_data(zeros)

        # Update the testbed state
        self.__update_iris_state(zeros)

        if return_zeros:
            return zeros


    def _close(self):
        """Close connection safely."""
        self._zero()  # First zero out IrisAO

        self.dm.stdin.write(b'quit\n')
        self.dm.stdin.close()
        print('Closing Iris AO.')
        self.__close_iris_controller_testbed_state()


    def apply_shape(self, command_object, dm_num=None):
        #TODO: Do I need to include dm_num here for compatibility?
        """
        Apply a command object to the Iris AO after adding the flatmap from the configfile.
        The units of said IrisCommand object are mrad for tip/tilt, um for piston.

        :param command_object: instance of IrisCommand class
        """
        if dm_num:
            raise NotImplementedError("dm_num is not implmented for the Iris AO")

        # Use DmCommand class to format the single command correctly.
        command = command_object.to_command()

        # Send array to DM.
        self.send_data(command)

        # Update the dm_command class attribute.
        self.command = command

        # Update the testbed_state.
        self.__update_iris_state(command_object)


    def apply_shape_to_both(self):
        """ Method only used by the BostomDmController"""
        raise NotImplementedError("apply_shape_to_both is not implmented for the Iris AO")


    @staticmethod
    def __update_iris_state(command_object):
        testbed_state.iris_command_object = command_object

    @staticmethod
    def __close_iris_controller_testbed_state():
        testbed_state.iris_command_object = None
