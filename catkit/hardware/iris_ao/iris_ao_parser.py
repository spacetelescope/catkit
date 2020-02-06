"""
Here there are several functions that can read in IrisAO commands that are in the form

- .PTT111 file: File format of the command coming out of the IrisAO GUI
- .ini file: File format of command that gets sent to the IrisAO controls
- array: Format that POPPY outputs if generating command in POPPY

Each of these formats can be used and have different formats. read_command takes in
any of these three formats and converts it to a dictionary of the form:
        {seg:(piston, tip, tilt)}
"""

from configparser import ConfigParser
import re

import astropy.units as u
import numpy as np

from catkit.hardware.iris_ao import util


# Functions for reading the .PTT11 file
def __clean_string(line):
    """
    Convenience function - not sure what it is doing
    """
    return re.sub(r"[\n\t\s]*", "", line)


def __convert_to_float(string):
    """Convert a string to a float, if possible
    """
    return float(string) if string else 0.0


def read_global(path):
    """
    This section of a PTT111 file only has one line and it’s called GV.
    This is a uniform ptt command that goes on all the segments. This dm_function
    reads that line.

    Example: [GV: 0, 0, 0]
    """
    with open(path, "r") as irisao_file:
        # Read global line
        raw_line = irisao_file.readline()

        # Clean up the string.
        clean_first_line = __clean_string(raw_line)

        # Check that the type is "GV"
        if clean_first_line[1:3].upper() == "GV":

            # Remove white space, and split the values.
            global_values = clean_first_line.lstrip("[GV:").rstrip("]").split(",")
            global_float = tuple(map(__convert_to_float, global_values))

            # If all zeros, then move on to the zernikes.
            if not all(v == 0 for v in global_float):
                return global_float
            else:
                return None

        else:
            raise Exception("Iris AO file formatting problem, can't process the global line:\n" + raw_line)


def read_zerkines(path):
    """
    The section of a PTT111 file has one number per global Zernike mode, which are called MV.
    read_zernikes() reads those numbers directly, which is only useful if teh value gets passed
    directly back into the IrisAO hardware control, as we can’t read which individual segment
    has what ptt command

    Example: [MV: 1, 0]
    """
    with open(path, "r") as irisao_file:
        raw_line = irisao_file.readline()
        clean_line = __clean_string(raw_line)

        # Skip to the zernike section:
        while clean_line[1:3].upper() != "MV":
            raw_line = irisao_file.readline()
            clean_line = __clean_string(raw_line)

        zernike_commands = []
        while clean_line[1:3].upper() == "MV":

            # Parse line and create of tuples (zernike, value).
            zernike_string_list = clean_line.lstrip("[MV:").rstrip("]").split(",")
            zernike_type = int(zernike_string_list[0])
            zernike_value = __convert_to_float(zernike_string_list[1])

            if zernike_value != 0:
                zernike_commands.append((zernike_type, zernike_value))

            raw_line = irisao_file.readline()
            clean_line = __clean_string(raw_line)

        if zernike_commands:
            return zernike_commands
        else:
            return None


def read_segments(path):
    """
    Read the zerinke values for P T T for each segment
    In this section of a PTT111 file, each segment gets a ptt command (ZV), which
    is read by this function. In this case, the lines are populated with the segment
    number, piston, tip, tilt.

    Example : [ZV: 1, 0, 0, 0]
    """
    with open(path, "r") as irisao_file:
        raw_line = irisao_file.readline()
        clean_line = __clean_string(raw_line)

        # Skip to the segment section:
        while clean_line[1:3].upper() != "ZV":
            raw_line = irisao_file.readline()
            clean_line = __clean_string(raw_line)

        segment_commands = {}
        while clean_line[1:3].upper() == "ZV":

            # Parse into dictionary {segment: (piston, tip, tilt)}.
            segment_string_list = clean_line.lstrip("[ZV:").rstrip("]").split(",")
            segment_num = int(segment_string_list[0])
            segment_tuple = __convert_to_float(segment_string_list[1]), \
                            __convert_to_float(segment_string_list[2]), \
                            __convert_to_float(segment_string_list[3])

            if any(segment_tuple):
                segment_commands[segment_num] = segment_tuple

            raw_line = irisao_file.readline()
            clean_line = __clean_string(raw_line)

        if segment_commands:
            # Prepare command for segments.
            return segment_commands
        else:
            return None


def read_ptt111(path):
    """
    Read the entirety of a PTT111 file
    """

    # Read the global portion of the file, and return the command if it's present.
    global_command = read_global(path)
    if global_command is not None:

        # Create a dictionary and apply global commands to all segments.
        command_dict = {}
        for i in range(util.IRIS_NUM_SEGMENTS):
            command_dict[i + 1] = global_command
        return command_dict

    # Read in the zernike aka "modal" lines and do error checking.
    zernike_commands = read_zerkines(path)
    if zernike_commands is not None:
        return zernike_commands

    # Read in the segment commands.
    segment_commands = read_segments(path)
    if segment_commands is not None:
        return segment_commands

    # No command found in file.
    return None


# Functions for reading ini file
def read_ini(path):
    """
    Read the Iris AO segment PTT parameters from an .ini file into Iris AO style
    dictionary {segnum: (piston, tip, tilt)}.

    This expects 37 segments with centering such that it is in the center of the IrisAO

    :param path: path and filename of ini file to be read
    :return command_dict: dict; {segnum: (piston, tip, tilt)}
    """
    config = ConfigParser()
    config.optionxform = str   # keep capital letters
    config.read(path)

    command_dict = {}
    for i in range(util.IRIS_NUM_SEGMENTS):
        section = 'Segment{}'.format(i+1)
        piston = float(config.get(section, 'z'))
        tip = float(config.get(section, 'xrad'))
        tilt = float(config.get(section, 'yrad'))
        command_dict[i+1] = (piston, tip, tilt)

    return command_dict


#Read a POPPY-created array
def read_poppy_array(array):
    """
    Read in an array produced by POPPY for the number of segments in your pupil.
    Each entry in array is a tuple of (piston, tip, tilt) values for that segment.
    Segment numbering is TO BE DETERMINED

    Will convert the values in this array from si units to um and mrad, as expected
    by IrisAO.

    :param array: array, of length number of segments in pupil. Units of: ([m], [rad], [rad])
    :return: dict; of the format {seg: (piston, tip, tilt)}
    """
    #The output from poppy
    #doesn't matter length  - that is figured out in segmented_dm_command
    #TODO: Check with Iva, which array should segnum be for outputs from Poppy

    command_dict = util.create_dict_from_array(array, seglist=None)

    # Convert from meters and radians (what Poppy outputs) to um and mrad.
    command_dict = convert_dict_from_si(command_dict)

    # Round to 3 decimal points after zero.
    rounded = {seg: (np.round(ptt[0], 3), np.round(ptt[1], 3),
                     np.round(ptt[2], 3)) for seg, ptt in list(command_dict.items())}

    return rounded



def convert_dict_from_si(command_dict):
    """
    Take a wf dict and convert from SI (meters and radians) to microns and millirads
    """
    converted = {seg: (ptt[0]*(u.m).to(u.um), ptt[1]*(u.rad).to(u.mrad), ptt[2]*(u.rad).to(u.mrad)) for
                 seg, ptt in list(command_dict.items())}

    return converted


def read_command(command):
    """
    Take in command that can be .PTT111, .ini, or array (of length #of segments in pupil)
    Dictionary units must all be the same (microns and millirads?)

    :param command: str, list, np.ndarray. Can be .PTT111, .ini files or array
    :return command_dict: dict, command in the form of a dictionary
    """
    try:
        if command.endswith("PTT111"):
            command_dict = read_segments(command)
        elif command.endswith("ini"):
            command_dict = read_ini(command)
        else:
            raise Exception("The command input format is not supported")
    except AttributeError:
        if isinstance(command, (list, tuple, np.ndarray)):
            command_dict = read_poppy_array(command)
        else:
            raise Exception("The command input format is not supported")

    return command_dict
