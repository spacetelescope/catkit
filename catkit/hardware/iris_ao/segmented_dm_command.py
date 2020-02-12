"""
Holds the class IrisCommand that is used to create a dict that will be sent to the
IrisAO hardware as a command.
"""

import json
import numpy as np

from catkit.config import CONFIG_INI
from catkit.hardware.iris_ao import util


class IrisCommand(object):
    """
    Handle converting inputs into expected dictionary format to be sent to the Iris AO

    :attribute data: dict, Input data, shifted if custom pupil exists in config file
    :attribute flat_map: bool, whether or not to apply the flat map
    :attribute source_pupil_numbering: list, numbering native to data
    :attribute command: dict, Final command with flat if flat_map = True and shift if applicable
    :attribute filename_flat: str, path to flat
    :attribute number_segments: int, number of segments in DM
    :attribute segments_in_pupil: int, number of segments in the pupil

    Optional if not using full DM:
    :attribute number_segments_in_pupil: int, the nubmer of segments in the pupil.

    """
    def __init__(self, data=None, flat_map=False, source_pupil_numbering=None):
        """
        Handle Iris AO specific commands in terms of piston, tip and tilt (PTT) per
        each segment. Creates a Iris AO-style command -{seg: (piston, tip, tilt)} -
        that can be loaded onto the hardware.

        Units are expect to be in um (for piston) and mrad (for tip and tilt)

        :param data: dict, of the form {seg: (piston, tip, tilt)}. If None, will populate
                     with dictionary of zeros for the segments used (This may be used if
                     only adding the flat map)
        :param flat_map: If true, add flat map correction to the data before creating command
        :param source_pupil_numbering: list, if a specific (non-Iris AO native) numbering
                                       exists for this command, pass it in here. This is
                                       particularly necessary for a command created with POPPY
        """

        # Establish variables for pupil shifting
        self._shift_center = False
        if not source_pupil_numbering:
            source_pupil_numbering = util.iris_pupil_numbering()
        self.source_pupil_numbering = source_pupil_numbering

        # Grab things from CONFIG_INI
        config_id = 'iris_ao'
        self.filename_flat = CONFIG_INI.get(config_id, 'flat_file_ini') #format is .ini

        # Define aperture - full iris or subaperture
        self.number_segments = CONFIG_INI.getint(config_id, 'number_of_segments')

        # If you are not using the full aperture, must include which segments are used
        try:
            self.segments_in_pupil = json.loads(CONFIG_INI.get(config_id, 'segments_in_pupil'))
            self.number_segments_in_pupil = CONFIG_INI.get(config_id, 'number_of_segments_pupil')
            if len(data) != len(self.segments_in_pupil):
                raise Exception("The number of segments in your command MUST equal number of segments in the pupil")
            if self.segments_in_pupil[0] != 1:
                self._shift_center = True # Pupil is centered elsewhere, must shift
        except Exception: #specifically NoOptionError but not recognized
            self.segments_in_pupil = util.iris_pupil_numbering()

        if not data:
            # If no data given, return dictionary of zeros
            array = np.zeros((util.iris_num_segments()), dtype=(float, 3))
            data = util.create_dict_from_array(array, seglist=self.segments_in_pupil)

        self.data = data
        self.flat_map = flat_map

        if self._shift_center:
            self.data = shift_command(self.data, self.segments_in_pupil,
                                      self.source_pupil_numbering)


    def get_data(self):
        """ Read it!
        """
        return self.data


    def to_command(self):
        """ Output command suitable for sending to the hardware driver
        """
        # Apply Flat Map
        if self.flat_map:
            self.add_map(self.filename_flat, flat=True)

        return self.data


    def add_map(self, new_command, flat=False):
        """
        Add a command to the one already loaded.

        Will shift the new command if you are using a shifted pupil. Updates self.data
        with combined commands.

        Will not shift the flat (flat=True) since the flat is segment-specific.

        :param new_command: str or array (.PTT111 or .ini file, or array from POPPY)
        :param flat: bool, only True if the map being added is the flat (so that it is not shifted)
        """
        data1 = self.get_data()
        data2, _ = util.read_command(new_command)

        if self._shift_center and not flat:
            data2 = shift_command(data2, self.segments_in_pupil, self.source_pupil_numbering)

        # Do magic adding only if segment exists in both
        combined_data = {seg: tuple(np.asarray(data1.get(seg, (0., 0., 0.))) + np.asarray(data2.get(seg, (0., 0., 0.)))) for seg in set(data1) & set(data2)}

        self.data = combined_data


def shift_command(command_to_shift, to_pupil, from_pupil=None):
    """
    If using a custom pupil, you must shift the numbering from centering in the center
    of the Iris AO, to the center of your pupil.

    This function will either shift the pupil from being centered on the IrisAo
    to the custom center (shift_to_hardware = True), or will shift from the custom
    center to the center of the IrisAO (shift_to_hardware = False, USAGE UNKNOWN)

    Different pupil numbering systems include:
    Full Iris: <= 37 segments centered on 1 and numbered from 1-19 (and until 37)
               for overall Iris AO pupil. This is the default "from_pupil"
               if None is given. This numbering is given by util.iris_pupil_numbering
    Custom: >=19 segments centered on first segment number in "segments_in_pupil" in
            the config file and numbered specifically for a custom pupil, defining
            the custom pupil as part of the DM
    Poppy: POPPY uses a different numbering scheme given by util.poppy_numbering

    :param command_to_shift: dict, wavefront map to be shifted, Iris AO format
    :param to_pupil: list, of segments in the pupil, starting at center and then
                         continuing counter clockwise
    :param from_pupil: list, segments in the pupil with numbering system you are moving from.
                       If None (default) the Iris AO numbering will be used

    :return: dict, command shifted to expected center
    """
    if from_pupil is None:
        from_pupil = util.iris_pupil_numbering()

    # Match lengths of arrays
    from_pupil, to_pupil = util.match_lengths(from_pupil, to_pupil)

    mapping = util.map_to_new_center(to_pupil, from_pupil)

    # Create the new map with the mapping of the input
    shifted_map = util.create_new_dictionary(command_to_shift, mapping)

    return shifted_map


def load_command(command, flat_map=True):
    """
    Loads a command from a file or array and returns a IrisCommand object.

    :param command: str, list, np.ndarray, dict. Can be .PTT111, .ini files, array from POPPY,
                    or dictionary of the same form as the output
    :param flat_map: Apply a flat map in addition to the data.

    :return: IrisCommand object representing the command dictionary.
    """
    data, source_pupil_numbering = util.read_command(command)
    return IrisCommand(data, flat_map=flat_map, source_pupil_numbering=source_pupil_numbering)
