import subprocess

import numpy as np

from catkit.hardware import testbed_state
from catkit.interfaces.SegmentedDeformableMirrorController import SegmentedDeformableMirrorController

from catkit.config import CONFIG_INI
from catkit.hardware.iris_ao import util

# import irisao library?

"""Interface for IrisAO segmented deformable mirror controller.
"""


class IrisAoController(SegmentedDeformableMirrorController):

    #instrument_lib = iao #TODO: what I import for irisAO software - if anything

    def initialize(self):
        """ Initialize dm manufacturer specific object - this does not, nor should it, open a connection."""
        self.log.info("Opening IrisAO connection")
        # Create class attributes for storing an individual command.
        self.command = None

        self.mirror_serial = CONFIG_INI.get('iris_ao', 'mirror_serial')
        self.driver_serial = CONFIG_INI.get('iris_ao', 'driver_serial')

        self.disableHardware = 'false' # For the suprocess call
        self.path_to_dm_exe = CONFIG_INI.get('iris_ao', 'path_to_dm_exe')
        self.full_path_dm_exe = CONFIG_INI.get('iris_ao', 'full_path_dm_exe')
        self.filename_ptt_dm = CONFIG_INI.get('iris_ao', 'c_code_ptt_file')

        self.dm = None


    def send_data(self, data):
        """ To send data to the IrisAO, you must write to the ConfigPTT.ini file
        and then use stdin.write(b'config\n') and stdin.flush() to send the command
        """
        # Write to ConfigPTT.ini
        util.write_ini_from_dict(data, path=self.filename_ptt_dm)

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


    def _zero(self, return_zeros=False):
        """Zero out dm"""
        # Set the DM to zeros.
        #zeros = {seg: (0.0, 0.0, 0.0) for seg in range(1, self.segnum+1)} #TODO: Make this a command object?
        array = np.zeros((util.IRIS_NUM_SEGMENTS), dtype=(float, 3))
        zeros = util.create_dict_from_array(array)
        self.send_data(zeros)

        if return_zeros:
            return zeros


    def _close(self):
        """Close connection safely."""
        self._zero()  # First zero out IrisAO

        self.dm.stdin.write(b'quit\n')
        self.dm.stdin.close()
        print('Closing Iris AO.')
        # self.__close_dm_controller_testbed_state()


    def apply_shape(self, command_object):
        """
        Apply a command object to the Iris AO after adding the flatmap from the configfile.

        The units of said IrisWavefront object are per default mrad for tip/tilt, um for piston.

        :param command_object: instance of IrisCommand class
        """
        # Use DmCommand class to format the single command correctly.
        command = command_object.to_command()

        # Send array to DM.
        self.send_data(command)

        # Update the dm_command class attribute.
        self.command = command

        # Update the testbed_state.
        self.__update_dm_state(command_object)


    #TODO: Do I need the below? I don't have dm_command-object in my testbed state
    # @staticmethod
    # def __update_dm_state(dm_command_object):
    #     testbed_state.dm_command_object = dm_command_object
    #
    # @staticmethod
    # def __close_dm_controller_testbed_state():
    #     testbed_state.dm_command_object = None
