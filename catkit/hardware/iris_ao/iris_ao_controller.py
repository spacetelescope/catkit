import numpy as np

from catkit.hardware import testbed_state
from catkit.interfaces.SegmentedDeformableMirrorController import SegmentedDeformableMirrorController

from catkit.config import CONFIG_INI

# import irisao library?

"""Interface for IrisAO segmented deformable mirror controller.
"""


class IrisAoController(SegmentedDeformableMirrorController):

    #instrument_lib = iao #TODO: what I import for irisAO software - if anything

    def initialize(self):
        """ Initialize dm manufacturer specific object - this does not, nor should it, open a connection."""
        self.log.info("Opening IrisAO connection")
        # Create class attributes for storing individual DM commands.
        self.dm_command = None
        self.mirror_serial = CONFIG_INI.get('iris_ao', 'mirror_serial')
        self.driver_serial = CONFIG_INI.get('iris_ao', 'driver_serial')

        self.disableHardware = 'false'
        self.DMexePath = CONFIG_INI.get('iris_ao', 'path_to_dm_exe')
        self.filename_ptt_dm = CONFIG_INI.get('iris_ao', 'c_code_ptt_file')
        self.dm = None

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
        write_ini_from_dict(data, path=self.filename_ptt_dm)

        # Apply the written .ini file to DM
        self.dm.stdin.write(b'config\n')
        self.dm.stdin.flush()

    def write_ini_from_dict(data, path):
        """
        Write a new ini file containing the dict wf map.

        segments: <=37 -> 37
        mapping: globalcen
        :param wfmap: dict; wavefront map in Iris AO format
        :param path: full path incl. filename to save the configfile to
        :return:
        """

        print("Creating config file: {}".format(path))
        mirror_serial = CONFIG_INI.get('iris_ao', 'mirror_serial')
        driver_serial = CONFIG_INI.get('iris_ao', 'driver_serial')

        config = ConfigParser()
        config.optionxform = str   # keep capital letters

        config.add_section('Param')
        config.set('Param', 'nbSegment', str(37))   # Iris AO has 37 segments

        config.add_section('SerialNb')
        config.set('SerialNb', 'mirrorSerial', mirror_serial)
        config.set('SerialNb', 'driverSerial', driver_serial)

        for i in range(1, 38):

            # If the segment number is present in the dictionary
            if i in list(wfmap.keys()):

                ptt = wfmap.get(i)
                section = 'Segment%d' % i
                config.add_section(section)
                config.set(section, 'z', str(np.round(ptt[0], decimals=3)))
                config.set(section, 'xrad', str(np.round(ptt[1], decimals=3)))
                config.set(section, 'yrad', str(np.round(ptt[2], decimals=3)))

            # If the segment number is not present in dictionary, set it to 0.0
            else:
                section = 'Segment%d' % i
                config.add_section(section)
                config.set(section, 'z', str(0.0))
                config.set(section, 'xrad', str(0.0))
                config.set(section, 'yrad', str(0.0))

        # Save to a file
        with open(path, 'w') as configfile:
            config.write(configfile)

    def _open(self):
        #From JOST:
        self.dm = subprocess.Popen([CONFIG_INI.get('iris_ao', 'full_path_dm_exe'), self.disableHardware],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   cwd=self.DMexePath, bufsize=1)

        #From HiCAT
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

        #From jost:
        exc_type, exc_val, exc_tb):
        self.dm.stdin.write(b'quit\n')
        self.dm.stdin.close()
        print('Closing Iris AO.')

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


    def apply_dict(self, command_object, flatmap_switch=True):
        """
        Apply a jost IrisWavefront object to the Iris AO after adding the flatmap from the configfile.

        The units of said IrisWavefront object are per default mrad for tip/tilt, um for piston, which is what is needed
        to have this work.
        Args:
            iriswf (instance of jost IrisWavefront class): PTT wavefront to be applied to Iris AO
            flatmap_switch (bool): defaults to True; determines whether to apply the flatmap before loading input map
        """

        # Create total wf map to go on the DM
        total_map = IrisWavefront()
        total_map.copy(iriswf)

        # Make sure we are in hardware mode (in order to have the correct segment mapping).
        if total_map.mode in ('custom', 'full'):
            pass
        elif total_map.mode == 'sim':
            total_map.map_to_hardware()
        else:
            raise Exception('This wavefront object has no valid mode specified.')

        # Add the flatmap (units: mrad for tip/tilt, um for piston)
        if flatmap_switch:
            flat_map = IrisWavefront()
            flat_map.read_ini(self.filename_flat)
            total_map.add_map(flat_map)

        # Write to ConfigPTT.ini
        write_ini_from_dict(total_map.wfmap, path=self.filename_ptt_dm)

        # Apply the written .ini file to DM
        self.dm.stdin.write(b'config\n')
        self.dm.stdin.flush()



    @staticmethod
    def __update_dm_state(dm_command_object):
        testbed_state.dm_command_object = dm_command_object

    @staticmethod
    def __close_dm_controller_testbed_state():
        testbed_state.dm_command_object = None
