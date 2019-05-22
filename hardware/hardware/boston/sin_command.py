from __future__ import (absolute_import, division,
                        unicode_literals)

import math

import numpy as np
# noinspection PyUnresolvedReferences
from builtins import *
from scipy.ndimage.interpolation import rotate
# noinspection PyPackageRequirements
from skimage.transform import resize

from hicat import util
from hicat.hicat_types import units
from hicat.config import CONFIG_INI

from DmCommand import DmCommand

dm_config_id = "boston_kilo952"


def sin_command(sin_specification,
                dm_num=1,
                bias=False,
                flat_map=False,
                return_shortname=False,
                initial_data=None):
    """
    Creates a 2D sine wave as a numpy array of the dimensions of the Boston DM with the DM pupil mask applied. Multiple
    sine waves can be applied by passing in a list of SinSpecifications, rather than a single instance.
    :param sin_specification: Can either be a list or a single specification (of type SinSpecification).
    :param dm_num: Default is 1.
    :param bias: Boolean flag to use constant voltage to apply to all actuators. Value retrieved from ini "bias_volts".
    :param flat_map: Boolean flag to use the appropriate characterized flat map for the DM.
    :param return_shortname: Boolean flag to return a string representation of the sinewave (good for filenames).
    :param initial_data: Pass in numpy array to start with, the new sin command will be added to it and returned.
    :return: Numpy array of the sine wave, (optional) metadata list, (optional) shortname.
    """

    # If a single specification is passed in, turn it into a list of 1.
    if not isinstance(sin_specification, list):
        sin_specification = [sin_specification]

    # Create an array of zeros.
    num_actuators_pupil = CONFIG_INI.getint(dm_config_id, 'dm_length_actuators')
    sin_wave = np.zeros((num_actuators_pupil, num_actuators_pupil))
    if initial_data is not None:
        sin_wave += initial_data

    # Add up the passed sine specifications to one sine wave
    for spec in sin_specification:

        # Make sure the requested command is properly sampled on the DM.
        if spec.ncycles > 17:
            raise ValueError("Cannot do more than 17 cycles per pupil on DM with 34 actuators across.")

        elif spec.ncycles >= 17 and spec.phase < 90:    # We can only do phase=90 if ncycles=17
            raise ValueError("Cosine (phase ~= 0) will not be sampled correctly at 17 cycles per pupil.")

        sin_wave += __sin_wave(spec.angle,
                               spec.ncycles,
                               spec.peak_to_valley,
                               spec.phase)

    # Apply the DM pupil mask.
    mask = util.get_hicat_dm_mask()
    sin_wave *= mask

    # Create the DM Command Object.
    dm_command_object = DmCommand(sin_wave, dm_num, flat_map=flat_map, bias=bias, sin_specification=sin_specification)

    if return_shortname:
        # Create short_name.
        short_name = "sin{}_rot{}_p2v{}nm".format(
            "_".join([str(round(x.ncycles, 2)) for x in sin_specification]),
            "_".join([str(round(x.angle, 2)) for x in sin_specification]),
            "_".join([str(round(x.peak_to_valley.to(units.nanometer).m, 2)) for x in sin_specification]))
        if flat_map:
            short_name += "_flat_map"
        if bias:
            bias_name = "bias_volts_dm1" if dm_num == 1 else "bias_volts_dm2"
            bias_volts = CONFIG_INI.getint(dm_config_id, bias_name)
            short_name += "_bias" + str(bias_volts)
        return dm_command_object, short_name
    else:
        return dm_command_object


def __sin_wave_aj_matlab(rotate_deg, ncycles, amplitude_factor):
    """
    Depricated - This function creates an imperfect sine wave due to numpy resize and rotate. Use __sin_wave().
    """
    fl6 = CONFIG_INI.getfloat('optical_design', 'focal_length6')
    fl7 = CONFIG_INI.getfloat('optical_design', 'focal_length7')

    # Create Sin Wave.
    num_actuators_pupil = CONFIG_INI.getint(dm_config_id, 'dm_length_actuators')
    ddms = num_actuators_pupil * float(300e-6)
    dapod = 1.025 * float(18e-3)
    apod_length = 256
    ndm = 2 * math.floor((fl6 / fl7) * ddms / (dapod / apod_length) / 2)
    xs = (np.arange(-ndm + 1, ndm, step=1.0) - 1 / 2) / (2 * ndm)

    xs, ys = np.meshgrid(xs, xs)
    value = float(ncycles) * (num_actuators_pupil / 26.65) * 2.0 * np.pi
    angle_grid = value * xs
    sin_wave = amplitude_factor * np.cos(angle_grid)

    sin_wave = rotate(sin_wave, rotate_deg, reshape=False)
    sin_wave_v = resize(sin_wave, (num_actuators_pupil, num_actuators_pupil), order=1, preserve_range=True,
                        mode="constant")

    # Flip.
    sin_wave_v = np.flipud(sin_wave_v)
    return sin_wave_v


def __sin_wave(rotate_deg, ncycles, peak_to_valley, phase):
    """
    Mathematical function to create a 2D sine wave the size of the HiCAT pupil.
    :param rotate_deg: Angle to rotate 2D sine wave in degrees.
    :param ncycles: Frequency in number of cycles.
    :param peak_to_valley: Amplitude multiplier pint quantity with base units of meters.
    :param phase: Phase in degrees. Note: phase = 0 produces a symmetrical cosine. phase = 90 produces a sine.
    :return: 2D numpy array sized by the "dm_length_actuators" parameter in config.ini file.
    """

    # Make a linear ramp.
    num_actuators_pupil = CONFIG_INI.getint(dm_config_id, 'dm_length_actuators')
    linear_ramp = np.linspace(-0.5, 0.5, num=num_actuators_pupil, endpoint=False)
    linear_ramp += 0.5/num_actuators_pupil

    # Convert to radians.
    phase_rad = np.deg2rad(phase)
    theta_rad = np.deg2rad(rotate_deg)

    # Create a 2D ramp.
    x_mesh, y_mesh = np.meshgrid(linear_ramp, linear_ramp)

    # Put the ramps through sine.
    xt = x_mesh * np.cos(theta_rad)
    yt = y_mesh * np.sin(theta_rad)
    xyt = xt + yt
    xyf = xyt * float(ncycles) * 2.0 * np.pi
    sine_wave = (float(peak_to_valley.to_base_units().m) / 2.0) * np.cos(xyf + phase_rad)
    return sine_wave
