"""
Utility functions to be used for creating commands for and controlling the IrisAO hardware
"""
from configparser import ConfigParser
import re

import astropy.units as u
import numpy as np

from catkit.config import CONFIG_INI


def iris_num_segments(dm_config_id='iris_ao'):
    """Number of segments in your Iris AO"""
    return CONFIG_INI.getint(dm_config_id, 'total_number_of_segments')


def iris_pupil_naming(dm_config_id='iris_ao'):
    """Naming of the Iris AO pupil starting at the center of the pupil and working
    outward in a clockwise direction. This is dependent on your IRISAO and the number
    of segments it has. This module has not yet been tested for the PTT489
    IrisAO model though it supports up to 163 segments."""
    num_segs = iris_num_segments(dm_config_id)
    seg_names = np.concatenate((np.array([1, 2]), np.flip(np.arange(3, 8)),
                                np.array([8]), np.flip(np.arange(9, 20)),
                                np.array([20]), np.flip(np.arange(21, 38)),
                                np.array([38]), np.flip(np.arange(39, 62)),
                                np.array([62]), np.flip(np.arange(63, 92)),
                                np.array([92]), np.flip(np.arange(93, 128)),
                                np.array([128]), np.flip(np.arange(129, 164))))

    return seg_names[:num_segs]


def create_dict_from_array(array, seglist=None):
    """
    Take an array of len number of segments, with a tuple of piston, tip, tilt
    and convert to a dictionary

    Seglist is a list of equal length with a single value equal to the segment number
    for the index in the array. If seglist is None, will asssume Iris AO numbering

    :param array: np.ndarry, array with length equal to number of segments in the pupil
                  with each entry a tuple of piston, tip, tilt values.
    :param seglist: list, list of segment numbers to grab from the array where the segment
                    number in the array is given by the index of the tuple

    :return: dict, command in the form of a dictionary of the form
             {seg: (piston, tip, tilt)}
    """
    if seglist is None:
        seglist = np.arange(len(array))+1

    # Put surface information in dict
    command_dict = {seg: tuple(ptt) for seg, ptt in zip(seglist, array)}

    return command_dict


def create_zero_array(number_of_segments):
    """
    Create an array of zeros for the Iris AO

    :param number_of_segments: int, the number of segments in your pupil
    :return: array of zeros the length of the number of total segments in the DM
    """
    return [(0., 0., 0.)] * number_of_segments


def write_ini(data, path, dm_config_id='iris_ao', mirror_serial=None, driver_serial=None):
    """
    Write a new ConfigPTT.ini file containing the command for the Iris AO.

    :param data: dict, wavefront map in Iris AO format
    :param path: full path incl. filename to save the configfile to
    :param mirror_serial: serial number of the Iris AO
    :param driver_serial: serial number of the driver used for the Iris AO
    """
    if not mirror_serial and not driver_serial:
        mirror_serial = CONFIG_INI.get(dm_config_id, "mirror_serial")
        driver_serial = CONFIG_INI.get(dm_config_id, "driver_serial")

    config = ConfigParser()
    config.optionxform = str   # keep capital letters

    config.add_section('Param')
    config.set('Param', 'nbSegment', str(iris_num_segments(dm_config_id)))

    config.add_section('SerialNb')
    config.set('SerialNb', 'mirrorSerial', mirror_serial)
    config.set('SerialNb', 'driverSerial', driver_serial)

    for i in iris_pupil_naming(dm_config_id):
        section = 'Segment{}'.format(i)
        config.add_section(section)
        # If the segment number is present in the dictionary
        if i in list(data.keys()):
            ptt = data.get(i)
            config.set(section, 'z', str(np.round(ptt[0], decimals=3)))
            config.set(section, 'xrad', str(np.round(ptt[1], decimals=3)))
            config.set(section, 'yrad', str(np.round(ptt[2], decimals=3)))
        # If the segment number is not present in dictionary, set it to 0.0
        else:
            config.set(section, 'z', str(0.0))
            config.set(section, 'xrad', str(0.0))
            config.set(section, 'yrad', str(0.0))

    # Save to a file
    with open(path, 'w') as configfile:
        config.write(configfile)


## Read commands
# Functions for reading the .PTT11 file
def clean_string(line):#filename, raw_line=False):
    """
    Delete "\n", "\t", and "\s" from a given line
    """
    return re.sub(r"[\n\t\s]*", "", line)


def convert_to_float(string):
    """Convert a string to a float, if possible
    """
    return float(string) if string else 0.0


def read_global(path):
    """
    This section of a PTT111 file only has one line and it’s called GV.
    This is a uniform ptt command that goes on all the segments. This dm_function
    reads that line.

    Example: [GV: 0, 0, 0]

    :param path: path to the PTT111 file

    :return: global commands if they exist
    """
    with open(path, "r") as irisao_file:
        # Read global line
        raw_line = irisao_file.readline()

        # Clean up the string.	        # Clean up the string.
        clean_first_line = clean_string(raw_line)
        # # Clean up the string.
        # clean_first_line, raw_line = clean_string(irisao_file, raw_line=True)

        # Check that the type is "GV"
        if clean_first_line[1:3].upper() == "GV":

            # Remove white space, and split the values.
            global_values = clean_first_line.lstrip("[GV:").rstrip("]").split(",")
            global_float = tuple(map(convert_to_float, global_values))

            # If all zeros, then move on to the zernikes.
            if not all(v == 0 for v in global_float):
                return global_float
            else:
                return None

        else:
            raise Exception("Iris AO file formatting problem, can't process the global line:\n" + raw_line)


def read_zernikes(path):
    """
    The section of a PTT111 file has one number per global Zernike mode, which are called MV.
    read_zernikes() reads those numbers directly, which is only useful if teh value gets passed
    directly back into the IrisAO hardware control, as we can’t read which individual segment
    has what ptt command

    Example: [MV: 1, 0]

    :param path: path to the PTT111 file

    :return: zernike commands if they exist
    """
    with open(path, "r") as irisao_file:
        raw_line = irisao_file.readline()
        clean_line = clean_string(raw_line)

        # Skip to the zernike section:
        while clean_line[1:3].upper() != "MV":
            raw_line = irisao_file.readline()
            clean_line = clean_string(raw_line)

        zernike_commands = []
        while clean_line[1:3].upper() == "MV":

            # Parse line and create of tuples (zernike, value).
            zernike_string_list = clean_line.lstrip("[MV:").rstrip("]").split(",")
            zernike_type = int(zernike_string_list[0])
            zernike_value = convert_to_float(zernike_string_list[1])

            if zernike_value != 0:
                zernike_commands.append((zernike_type, zernike_value))

            raw_line = irisao_file.readline()
            clean_line = clean_string(raw_line)

        if zernike_commands:
            return zernike_commands
        else:
            return None


def read_segments(path):
    """
    Read the zernike values for P T T for each segment
    In this section of a PTT111 file, each segment gets a ptt command (ZV), which
    is read by this function. In this case, the lines are populated with the segment
    number, piston, tip, tilt.

    Example : [ZV: 1, 0, 0, 0]

    :param path: path to the PTT111 file

    :return: segment commands if they exist
    """
    with open(path, "r") as irisao_file:
        raw_line = irisao_file.readline()
        clean_line = clean_string(raw_line)

        # Skip to the segment section:
        while clean_line[1:3].upper() != "ZV":
            raw_line = irisao_file.readline()
            clean_line = clean_string(raw_line)

        segment_commands = {}
        while clean_line[1:3].upper() == "ZV":

            # Parse into dictionary {segment: (piston, tip, tilt)}.
            segment_string_list = clean_line.lstrip("[ZV:").rstrip("]").split(",")
            segment_num = int(segment_string_list[0])
            segment_tuple = convert_to_float(segment_string_list[1]), \
                            convert_to_float(segment_string_list[2]), \
                            convert_to_float(segment_string_list[3])

            segment_commands[segment_num] = segment_tuple

            raw_line = irisao_file.readline()
            clean_line = clean_string(raw_line)

        if segment_commands:
            # Prepare command for segments.
            return segment_commands
        else:
            return None


def read_ptt111(path):
    """
    Read the entirety of a PTT111 file

    :param path: path to the PTT111 file

    :return: commands, if they exist
    """

    # Read the global portion of the file, and return the command if it's present.
    global_command = read_global(path)
    if global_command is not None:

        # Create a dictionary and apply global commands to all segments.
        command_dict = {}
        for i in range(iris_num_segments()):
            command_dict[i + 1] = global_command
        return command_dict

    # Read in the zernike aka "modal" lines and do error checking.
    zernike_commands = read_zernikes(path)
    if zernike_commands is not None:
        return zernike_commands

    # Read in the segment commands.
    segment_commands = read_segments(path)
    if segment_commands is not None:
        return segment_commands

    # No command found in file.
    return None


def read_ini(path):
    """
    Read the Iris AO segment PTT parameters from an .ini file into Iris AO style
    dictionary {segnum: (piston, tip, tilt)}.

    This expects 37 segments with centering such that it is in the center of the IrisAO

    :param path: path and filename of ini file to be read

    :return: dict, command in the form of a dictionary of the form {seg: (piston, tip, tilt)}
    """
    config = ConfigParser()
    config.optionxform = str   # keep capital letters
    config.read(path)

    command_dict = {}
    for i in range(iris_num_segments()):
        section = 'Segment{}'.format(i+1)
        piston = float(config.get(section, 'z'))
        tip = float(config.get(section, 'xrad'))
        tilt = float(config.get(section, 'yrad'))
        command_dict[i+1] = (piston, tip, tilt)

    return command_dict


def read_segment_values(segment_values):
    """
    Each of the following formats can be read in. This function takes in
    any of these three formats and converts it to a dictionary of the form:
            {seg:(piston, tip, tilt)}
    With units of : ([um], [mrad], [mrad])

    See the README for the semented dm for more details.

    - .PTT111/.PTT489 file: File format of the segments values coming out of the IrisAO GUI
    - .ini file: File format of segments values that gets sent to the IrisAO controls
    - dictionary: Same format that gets returned: {seg: (piston, tip, tilt)}

    :param segment_values: str, list. Can be .PTT111, .ini files or a list with piston, tip,
                           tilt values in a tuple for each segment. For the list, the first
                           element is the center or top of the innermost ring of the pupil,
                           and subsequent elements continue up and/or clockwise around the
                           pupil (see README for more information)

    :return: list, list, PTT tuples in list/array of the form (piston, tip, tilt)
                         the first element is the center or top of the innermost ring of
                         the pupil, and subsequent elements continue up and/or clockwise
                         around the pupil (see README for more information)
    """
    # Read in file
    if segment_values is None:
        ptt_list = create_nan_list(iris_num_segments())
        segment_names = None
    elif isinstance(segment_values, str):
        if segment_values.endswith("PTT111") or segment_values.endswith("PTT489"):
            command_dict = read_segments(segment_values)
        elif segment_values.endswith("ini"):
            command_dict = read_ini(segment_values)
        ptt_list = [*command_dict.values()]
        segment_names = [*command_dict.keys()]
    elif isinstance(segment_values, (np.ndarray, list)):
        ptt_list = segment_values
        segment_names = None
    else:
        raise TypeError("The segment values input format is not supported")

    return ptt_list, segment_names
