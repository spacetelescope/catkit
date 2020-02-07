"""
Utility functions to be used for controlling the IrisAO hardware
"""
from configparser import ConfigParser
import logging

import numpy as np

IRIS_NUM_SEGMENTS = 37
IRIS_PUPIL_NUMBERING = np.arange(IRIS_NUM_SEGMENTS)+1
POPPY_NUMBERING = [0,   # Ring 0
                   1, 6, 5, 4, 3, 2,  # Ring 1
                   7, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8,  # Ring 2
                   19, 36, 35, 34, 33, 32, 31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20]  # Ring 3

log = logging.getLogger(__name__)

def map_to_new_center(new_pupil, old_pupil):
    """
    Create a zipped dictionary of the pupil you moving to and the one you are moving
    from
    """
    return dict(zip(new_pupil, old_pupil))


def create_new_dictionary(original_command, mapping_dict):
    """
    Update the PTT dictionary segment numbers based on the mapping dictionary created
    by _map_to_new_center
    """
    return {seg: original_command.get(val, (0., 0., 0.)) for seg, val in list(mapping_dict.items())}


def create_dict_from_array(array, seglist=None):
    """
    Simple take an array of len number of segments, with a tupple of piston, tip, tilt
    and convert to a dictionary

    Seglist is a list of equal length with a single value equal to the segment number
    for the index in the array
    """
    if seglist is None:
        seglist = np.arange(len(array))

    # Put surface information in dict
    command_dict = {seg: tuple(ptt) for seg, ptt in zip(seglist, array)}

    return command_dict


def write_ini(data, path, mirror_serial, driver_serial):
    """
    Write a new ConfigPTT.ini file containing the command for the Iris AO.

    segments:
    :param data: dict; wavefront map in Iris AO format
    :param path: full path incl. filename to save the configfile to
    :return:
    """

    log.info("Creating config file: {}".format(path))

    config = ConfigParser()
    config.optionxform = str   # keep capital letters

    config.add_section('Param')
    config.set('Param', 'nbSegment', IRIS_NUM_SEGMENTS)   # Iris AO has 37 segments

    config.add_section('SerialNb')
    config.set('SerialNb', 'mirrorSerial', mirror_serial)
    config.set('SerialNb', 'driverSerial', driver_serial)

    for i in range(IRIS_PUPIL_NUMBERING):
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
