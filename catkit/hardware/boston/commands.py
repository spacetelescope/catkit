import numpy as np

from hicat.config import CONFIG_INI
from catkit.hardware.boston.DmCommand import DmCommand
from catkit.catkit_types import units, quantity

# Read config file once here.
config_name = "boston_kilo952"

# Load values from config.ini into variables.
num_actuators_pupil = CONFIG_INI.getint(config_name, 'dm_length_actuators')
total_actuators = CONFIG_INI.getint(config_name, 'number_of_actuators')


def flat_command(bias=False,
                 flat_map=False,
                 return_shortname=False,
                 dm_num=1):
    """
    Creates a DmCommand object for a flat command.
    :param bias: Boolean flag for whether to apply a bias.
    :param flat_map: Boolean flag for whether to apply a flat_map.
    :param return_shortname: Boolean flag that will return a string that describes the object as the second parameter.
    :param dm_num: 1 or 2, for DM1 or DM2.
    :return: DmCommand object, and optional descriptive string (good for filename).
    """

    short_name = "flat"

    # Bias.
    if flat_map:
        short_name += "_flat_map"
    if bias:
        short_name += "_bias"

    zero_array = np.zeros((num_actuators_pupil, num_actuators_pupil))
    dm_command_object = DmCommand(zero_array, dm_num, flat_map=flat_map, bias=bias)

    if return_shortname:
        return dm_command_object, short_name
    else:
        return dm_command_object


def poke_command(actuators, amplitude=quantity(700, units.nanometers), bias=False,
                 flat_map=True, return_shortname=False, dm_num=1):
    """
    Creates a DmCommand object that pokes actuators at a given amplitude.
    :param actuators: List of actuators, or a single actuator.
    :param amplitude: Nanometers of amplitude
    :param bias: Boolean flag for whether to apply a bias.
    :param flat_map: Boolean flag for whether to apply a flat_map.
    :param return_shortname: Boolean flag that will return a string that describes the object as the second parameter.
    :param dm_num: 1 or 2, for DM1 or DM2.
    :return: DmCommand object, and optional descriptive string (good for filename).
    """

    short_name = "poke"
    poke_array = np.zeros(total_actuators)

    # Convert peak the valley from a quantity to nanometers, and get the magnitude.
    amplitude = amplitude.to(units.meters).m

    # Bias.
    if flat_map:
        short_name += "_flat_map"
    if bias:
        short_name += "_bias"

    if isinstance(actuators, list):
        for actuator in actuators:
            poke_array[actuator] = amplitude
            short_name += "_" + str(actuator)
    else:
        short_name += "_" + str(actuators)
        poke_array[actuators] = amplitude

    dm_command_object = DmCommand(poke_array, dm_num, flat_map=flat_map, bias=bias)

    if return_shortname:
        return dm_command_object, short_name
    else:
        return dm_command_object


def poke_letter_f_command(amplitude=quantity(250, units.nanometers), bias=False, flat_map=True, dm_num=1):
    """
    Creates the letter F in normal orientation when viewed in DS9.
    """
    data = np.zeros((num_actuators_pupil, num_actuators_pupil))

    # Convert peak the valley from a quantity to nanometers, and get the magnitude.
    amplitude = amplitude.to(units.meters).m

    # Side
    data[10:24, 12] = amplitude

    # Top
    data[24, 12:22] = amplitude

    # Middle
    data[19, 12:17] = amplitude

    # Convert to 1d array and return a DmCommand object.
    return DmCommand(data, dm_num, flat_map=flat_map, bias=bias)


def checkerboard_command(amplitude=quantity(250, units.nanometers), bias=False, flat_map=True,
                         dm_num=1, offset_x=0, offset_y=3, step=4):
    """
    Creates a checkerboard pattern DM command.  Useful for phase retrieval or 4D images. Default values
    start with the zero index of the DM command ("first actuator").
    """
    data = np.zeros((num_actuators_pupil, num_actuators_pupil))

    # Convert peak the valley from a quantity to nanometers, and get the magnitude.
    amplitude = amplitude.to(units.meters).m

    data[offset_x::step, offset_y::step] = amplitude

    return DmCommand(data, dm_num, flat_map=flat_map, bias=bias)
