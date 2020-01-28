import numpy as np

from catkit.hardware import testbed_state
from catkit.interfaces.SegmentedDeformableMirrorController import SegmentedDeformableMirrorController

# import irisao library?

"""Interface for IrisAO segmented deformable mirror controller.
"""


class IrisAoController(SegmentedDeformableMirrorController):

    instrument_lib = iao #TODO: what I import for irisAO software - if anything

    def initialize(self, serial_number, command_length, dac_bit_width):
        """ Initialize dm manufacturer specific object - this does not, nor should it, open a connection."""
        self.log.info("Opening IrisAO connection")
        # Create class attributes for storing individual DM commands.
        self.dm_command = None
        self.serial_num = serial_number
        self.command_length = command_length
        self.dac_bit_width = dac_bit_width

    def send_data(self, data):
        """ To send data to the IrisAO, you must write to the ConfigPTT.ini file
        and then use stdin.write(b'config\n') and stdin.flush() to send the command
        """
        # # The DM controller expects the command to be unitless (normalized Volts): 0.0 - 1.0, where 1.0 := max_volts
        # data_min = np.min(data)
        # data_max = np.max(data)
        # if data_min < 0 or data_max > 1:
        #     self.log.warning(f"DM command out of range and will be clipped by hardware. min:{data_min}, max:{data_max}")
        #
        # status = self.instrument.send_data(data)
        # if status != self.instrument_lib.NO_ERR:
        #     raise Exception("{}: Failed to send data - {}".format(self.config_id,
        #                                                           self.instrument.error_string(status)))
        # Read command and do the things then write out
        # Write to ConfigPTT.ini
        write_ini_from_dict(total_map.wfmap, path=self.filename_ptt_dm)

        # Apply the written .ini file to DM
        self.dm.stdin.write(b'config\n')
        self.dm.stdin.flush()

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
        zeros = self._zero(return_zeros=True)

        # Store the current dm_command values in class attributes.
        self.dm_command = zeros
        self.dm_controller = self.instrument  # For legacy API purposes

        return self.instrument

    def _zero(self, return_zeros=False):
        """Zero out dm such that only flat is on the segments"""
        # Set the DM to zeros.
        #zeros = np.zeros(self.command_length, dtype=float)
        zeros = {seg: (0.0, 0.0, 0.0) for seg in range(1, self.segnum+1)}
        self.send_data(zeros)

        if return_zeros:
            return zeros

        # TODO: below is what is currently in jost.dm_functions
        # all_zero = IrisWavefront()
        # all_zero.zero()
        # self.apply_dict(all_zero)
        #

    def _close(self):
        """Close dm connection safely."""
        try:
            try:
                self.log.info("Closing DM connection")

                self._zero()
            finally:
                self.instrument.close_dm()
        finally:
            self.instrument = None
            # Update testbed_state.
            self.__close_dm_controller_testbed_state()


    def apply_shape(self, command_object):
        """Forms a command for a single DM, and re-sends the existing shape to other DM."""

        # Use DmCommand class to format the single command correctly.
        dm_command = dm_command_object.to_dm_command()

        # Send array to DM.
        self.send_data(dm_command)

        # Update the dm_command class attribute.
        self.dm_command = dm_command

        # Update the testbed_state.
        self.__update_dm_state(dm_command_object)

    @staticmethod
    def __update_dm_state(dm_command_object):
        testbed_state.dm_command_object = dm_command_object

    @staticmethod
    def __close_dm_controller_testbed_state():
        testbed_state.dm_command_object = None
