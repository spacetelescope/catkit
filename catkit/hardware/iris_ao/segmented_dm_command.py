"""
Holds the class IrisCommand that is used to create a dict that will be sent to the
IrisAO hardware as a command.
"""

import numpy as np

from catkit.config import CONFIG_INI
from catkit.hardware.iris_ao import iris_ao_parser, util


class IrisCommand(object):
    """
    Class that will deal with Iris AO specific wavefront maps in terms of piston, tip
    and tilt (PTT) per each segment. Expects a Iris AO-style command -
    {seg: (piston, tip, tilt)} - that can be loaded onto the hardware.

    Units are expect to be in um (for piston) and mrad (for tip and tilt)

    :param data: dict, of the form {seg: (piston, tip, tilt)}. If None, will populate
                 with dictionary of zeros for the segments used (This may be used if
                 only adding the flat map)
    :param flat_map: If true, add flat map correction to the data before creating command

    :attribute data: dict, Input data, shifted if custom pupil exists in config file
    :attribute flat_map: bool, whether or not to apply the flat map
    :attribute command: dict, Final command with flat if flat_map = True and shift if applicable

    :returns command_dict: dictionary
    """
    def __init__(self, data=None, flat_map=False):
        self._shift_center = False
        # Grab things from CONFIG_INI
        config_id = 'iris_ao'
        self.filename_flat = CONFIG_INI.get(config_id, 'flatfile_ini') #format is .ini

        # Define aperture - full iris or subaperture
        self.number_segments = CONFIG_INI.getint(config_id, 'nb_segments')

        # If you are not using the full aperture, must include which segments are used
        try:
            self.segments_used = CONFIG_INI.get(config_id, 'segments_used')
            self.number_segments_in_pupil = CONFIG_INI.get(config_id, 'pupil_nb_seg')
            if len(data) != len(self.segments_used):
                raise Exception("The number of segments in your command MUST equal number of segments in the pupil")
            if self.segments_used[0] != 1:
                self._shift_center = True # Pupil is centered elsewhere, must shift
        except Exception: #specifically NoOptionError but not recognized
            self.segments_used = util.IRIS_PUPIL_NUMBERING

        if not data:
            # If no data given, return dictionary of zeros
            array = np.zeros((util.IRIS_NUM_SEGMENTS), dtype=(float, 3))
            data = util.create_dict_from_array(array, seglist=self.segments_used)

        self.data = data
        self.flat_map = flat_map


        if self._shift_center:
            self.data = shift_command(self.data, self.segments_used)


    def get_data(self):
        """ Read it!
        """
        return self.data


    def to_command(self):
        """ Output command suitable for sending to the hardware driver
        """
        command = np.copy(self.data)

        # Apply Flat Map
        if self.flat_map:
            flat_map = iris_ao_parser.read_command(self.filename_flat) #convert to dict
            self.add_map(command, flat_map, flat=True)

        return command

    def add_map(self, old_command, new_command, flat=False):
        """
        Add a command to the one already loaded.

        Will shift the new command if you are using a shifted pupil. Updates self.data
        with combined commands.

        Will not shift the flat (flat=True) since the flat is segment-specific.

        :param new_command: str or array (.PTT111 or .ini file, or array from POPPY)
        """
        data1 = self.get_data
        data2 = iris_ao_parser.read_command(new_command)

        if self._shift_center and not flat:
            data2 = shift_command(data2, self.segments_used)

        # Do magic adding only if segment exists in both
        combined_data = {seg: tuple(np.asarray(data1.get(seg, (0., 0., 0.))) + np.asarray(data2.get(seg, (0., 0., 0.)))) for seg in set(data1) & set(data2)}

        self.data = combined_data

def shift_command(command_to_shift, custom_pupil, shift_to_hardware=True):
    """
    If using a custom pupil, you must shift the numbering from centering in the center
    of the Iris AO, to the center of your pupil.

    This function will either shift the pupil from being centered on the IrisAo
    to the custom center (shift_to_hardware = True), or will shift from the custom
    center to the center of the IrisAO (shift_to_hardware = False, USAGE UNKNOWN)

    The different pupils are:
    Full Iris pupil: <= 37 segments centered on 1 and numbered from 1-19 (and until 37)
                     for overall Iris AO pupil
    Custom pupil: >=19 segments centered on first segment number in "segments_used" in
                  the config file and numbered specifically for a custom pupil, defining
                  the custom pupil as part of the DM

    :param command_to_shift: dict, wavefront map to be shifted, Iris AO format
    :param custom_pupil: list, of segments in the pupil, starting at center and then
                         continuing counter clockwise
    :param shift_to_hardware: bool, if True (default) you are shifting from the full
                              Iris AO numbering to the specific pupil numbering

    :returns shifted_map: dict, command shifted to expected center
    """
    iris_numbering = util.IRIS_PUPIL_NUMBERING[:len(custom_pupil)]  # Match lengths of arrays

    if shift_to_hardware:
        mapping = util.map_to_new_center(custom_pupil, iris_numbering)
    else:
        mapping = util.map_to_new_center(iris_numbering, custom_pupil)

    # Create the new map with the mapping of the input
    shifted_map = util.create_new_dictionary(command_to_shift, mapping)

    return shifted_map


def load_command(command, flat_map=True):
    """
    Loads a command from a file or array and returns a IrisCommand object.

    :param command: str, list, np.ndarray. Can be .PTT111, .ini files or array from POPPY
    :param flat_map: Apply a flat map in addition to the data.

    :return: IrisCommand object representing the command dictionary.
    """
    data = iris_ao_parser.read_command(command)
    return IrisCommand(data, flat_map=flat_map)
