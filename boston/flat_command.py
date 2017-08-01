from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import numpy as np

from hicat import config as hicat_config
from .DmCommand import DmCommand

# Read config file once here.
config = hicat_config.load_config_ini()
config_name = "boston_kilo952"

# Load values from config.ini into variables.
num_actuators_pupil = config.getint(config_name, 'dm_length_actuators')


def flat_command(bias=False,
                 flat_map=False,
                 return_shortname=False,
                 dm_num=1):

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
