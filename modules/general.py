from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import os
from ...hicat_types import FpmPosition, ImageCentering
from ... import util
from ...hardware import testbed
from ...config import CONFIG_INI
from ...hardware.boston import commands
from ...hardware.boston import DmCommand


def take_exposures_dm_commands(dm2_command_list,
                               path,
                               exp_set_name,
                               coron_exp_time,
                               direct_exp_time,
                               list_of_paths=True,
                               num_exposures=10,
                               dm1_command_object=commands.flat_command(bias=False, flat_map=True),
                               camera_type="imaging_camera",
                               centering=ImageCentering.custom_apodizer_spots):
    for command in dm2_command_list:
        if list_of_paths:
            dm2_command_object = DmCommand.load_dm_command(command, bias=False, flat_map=False, dm_num=2, as_volts=True)
            filename = os.path.basename(command)
        else:
            dm2_command_object = command[0]
            filename = command[1]
        experiment_path = os.path.join(path, exp_set_name, filename)

        # Direct.
        take_exposures(dm1_command_object,
                       dm2_command_object,
                       direct_exp_time,
                       num_exposures,
                       camera_type,
                       False,
                       True,
                       experiment_path,
                       filename,
                       "direct",
                       suffix=None,
                       centering=ImageCentering.psf)

        # Coron.
        take_exposures(dm1_command_object,
                       dm2_command_object,
                       coron_exp_time,
                       num_exposures,
                       camera_type,
                       True,
                       True,
                       experiment_path,
                       filename,
                       "coron",
                       suffix=None,
                       centering=centering)


def take_exposures(dm1_command_object,
                   dm2_command_object,
                   exposure_time,
                   num_exposures,
                   camera_type,
                   coronograph,
                   pipeline,
                   path,
                   filename,
                   exposure_set_name,
                   suffix,
                   **kwargs):

    # Wait to set the path until the experiment starts (rather than the constructor)
    if path is None:
        suffix = "take_exposures_data" if suffix is None else "take_exposures_data_" + suffix
        path = util.create_data_path(suffix=suffix)

    util.setup_hicat_logging(path, "take_exposures_data")

    # Establish image type and set the FPM position and laser current
    if coronograph:
        fpm_position = FpmPosition.coron
        laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "coron_current")
        if exposure_set_name is None:
            exposure_set_name = "coron"
    else:
        fpm_position = FpmPosition.direct
        laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
        if exposure_set_name is None:
            exposure_set_name = "direct"

    # Take data
    with testbed.laser_source() as laser:
        laser.set_current(laser_current)

        with testbed.dm_controller() as dm:
            dm.apply_shape_to_both(dm1_command_object, dm2_command_object)
            testbed.run_hicat_imaging(exposure_time, num_exposures, fpm_position, path=path,
                                      filename=filename,
                                      exposure_set_name=exposure_set_name,
                                      camera_type=camera_type,
                                      pipeline=pipeline,
                                      **kwargs)
    return path
