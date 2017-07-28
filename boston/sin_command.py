from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

from collections import namedtuple

from builtins import *

import math
import os

import numpy as np
from astropy.io import fits
from scipy.ndimage.interpolation import rotate
from skimage.transform import resize

from hicat.hardware.boston.DmCommand import DmCommand
from hicat import config as hicat_config, util as hicat_util
from hicat import *  # Pulls in the root hicat __init.py__ stuff.

# Read config file once here.
config = hicat_config.load_config_ini()
config_name = "boston_kilo952"

# Load values from config.ini into variables.
num_actuators_pupil = config.getint(config_name, 'pupil_length_actuators')
total_actuators = config.getint(config_name, 'number_of_actuators')
fl6 = config.getfloat(config_name, 'focal_length6')
fl7 = config.getfloat(config_name, 'focal_length7')
command_length = config.getint(config_name, 'command_length')

# Get Script directory once here.
script_dir = os.path.dirname(__file__)

# Create the index952 from mask once here.
mask = fits.open(script_dir + '/kiloCdm_2Dmask.fits')[0].data
index952 = np.flatnonzero(mask)

# Named Tuple as a container for sine wave specifications. peak_to_valley must be a pint quantity.
SinSpecification = namedtuple("SinSpecification", "angle, ncycles, peak_to_valley, phase")


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
    :param bias: Boolean flag to use constant voltage to apply to all actuators. Value retrieved from ini "bias_volts".
    :param flat_map: Boolean flag to use the appropriate characterized flat map for the DM.
    :param return_shortname: Boolean flag to return a string representation of the sinewave (good for filenames).
    :return: Numpy array of the sine wave, (optional) metadata list, (optional) shortname.
    """

    # If a single specification is passed in, turn it into a list of 1.
    if not isinstance(sin_specification, list):
        sin_specification = [sin_specification]

    # Create an array of zeros.
    sin_wave = np.zeros((num_actuators_pupil, num_actuators_pupil))
    if initial_data is not None:
        sin_wave += initial_data

    for spec in sin_specification:

        sin_wave += __sin_wave(spec.angle,
                               spec.ncycles,
                               spec.peak_to_valley,
                               spec.phase)

    # Apply the DM pupil mask.
    sin_wave *= mask

    # Create the DM Command Object.
    dm_command_object = DmCommand(sin_wave, dm_num, flat_map=flat_map, bias=bias, sin_specification=sin_specification)

    if return_shortname:
        # Create short_name.
        short_name = "sin{}_rot{}_p2v{}nm".format(
            "_".join([str(round(x.ncycles,2)) for x in sin_specification]),
            "_".join([str(round(x.angle,2)) for x in sin_specification]),
            "_".join([str(round(x.peak_to_valley.to(units.nanometer).m,2)) for x in sin_specification]))
        if flat_map:
            short_name += "_flat_map"
        if bias:
            bias_volts = config.getint(config_name, "bias_volts")
            short_name += "_bias" + str(bias_volts)
        return dm_command_object, short_name
    else:
        return dm_command_object


def __sin_wave_aj_matlab(rotate_deg, ncycles, amplitude_factor):
    """
    Depricated - This function creates an imperfect sine wave due to numpy resize and rotate. Use __sin_wave().
    """
    # Create Sin Wave.
    Ddms = num_actuators_pupil * float(300e-6)
    Dapod = 1.025 * float(18e-3)
    apod_length = 256
    Ndm = 2 * math.floor((fl6 / fl7) * Ddms / (Dapod / apod_length) / 2)
    xs = (np.arange(-Ndm + 1, Ndm, step=1.0) - 1 / 2) / (2 * Ndm)

    XS, YS = np.meshgrid(xs, xs)
    value = float(ncycles) * (num_actuators_pupil / 26.65) * 2.0 * np.pi
    angle_grid = value * XS
    sinWave = amplitude_factor * np.cos(angle_grid)

    sinWave = rotate(sinWave, rotate_deg, reshape=False)
    sinWaveV = resize(sinWave, (num_actuators_pupil, num_actuators_pupil), order=1, preserve_range=True,
                      mode="constant")

    # Flip.
    sinWaveV = np.flipud(sinWaveV)
    return sinWaveV


def __sin_wave(rotate_deg, ncycles, peak_to_valley, phase):
    """
    Mathematical function to create a 2D sine wave the size of the HiCAT pupil.
    :param rotate_deg: Angle to rotate 2D sine wave in degrees.
    :param ncycles: Frequency in number of cycles.
    :param peak_to_valley: Amplitude multiplier pint quantity with base units of meters.
    :param phase: Phase in degrees.
    :return: 2D numpy array sized by the "pupil_length_actuators" parameter in config.ini file.
    """

    # Make a linear ramp.
    linear_ramp = np.linspace(-0.5, 0.5, num=num_actuators_pupil, endpoint=False)

    # Convert to radians.
    phase_rad = np.deg2rad(phase)
    theta_rad = np.deg2rad(rotate_deg)

    # Create a 2D ramp.
    x_mesh, y_mesh = np.meshgrid(linear_ramp, linear_ramp)

    # Put the ramps through sine.
    Xt = x_mesh * np.cos(theta_rad)
    Yt = y_mesh * np.sin(theta_rad)
    XYt = Xt + Yt
    XYf = XYt * float(ncycles) * 2.0 * np.pi
    sine_wave = (float(peak_to_valley.to_base_units().m) / 2.0) * np.cos(XYf + phase_rad)
    return sine_wave
