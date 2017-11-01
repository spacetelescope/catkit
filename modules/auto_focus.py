from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from shutil import copyfile

import os
from glob import glob

from ...hardware.boston.commands import flat_command
from ... import util
from ...hardware import testbed
from ...hicat_types import *
from ...config import CONFIG_INI


def take_auto_focus_data(bias,
                         flat_map,
                         exposure_time,
                         num_exposures,
                         position_list,
                         path,
                         camera_type,
                         **kwargs):
    # Wait to set the path until the experiment starts (rather than the constructor)
    if path is None:
        path = util.create_data_path(suffix="focus")

    with testbed.laser_source() as laser:
        direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
        laser.set_current(direct_laser_current)

        with testbed.motor_controller():
            # Initialize motors.
            print("Initialized motors for Auto Focus once, and will now only move the camera motor.")

        with testbed.dm_controller() as dm:
            dm_command_object = flat_command(bias=bias, flat_map=flat_map)
            dm.apply_shape(dm_command_object, 1)

            for i, position in enumerate(position_list):
                with testbed.motor_controller(initialize_to_nominal=False) as mc:
                    mc.absolute_move(testbed.get_camera_motor_name(camera_type), position)
                filename = "focus_" + str(int(position * 1000))
                metadata = MetaDataEntry("Camera Position", "CAM_POS", position * 1000, "Position * 1000")
                testbed.run_hicat_imaging(exposure_time, num_exposures, FpmPosition.direct, path=path,
                                          filename=filename,
                                          exposure_set_name="motor_" + str(int(position * 1000)),
                                          extra_metadata=metadata,
                                          init_motors=False,
                                          camera_type=camera_type,
                                          **kwargs)
    return path


def collect_final_images(path):
    results = [y for x in os.walk(path) for y in glob(os.path.join(x[0], "*_cal.fits"))]
    for img in results:
        copyfile(img, os.path.join(path, os.path.basename(img)))
