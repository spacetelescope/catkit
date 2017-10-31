from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import numpy as np

from .Experiment import Experiment
from ..hicat_types import *
from .. import util
from ..hardware import testbed
from ..config import CONFIG_INI


class TakeExposures(Experiment):
    name = "Take Phase Retrieval Data"

    def __init__(self,
                 dm_command_object,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=5,
                 path=None,
                 image_type="coron",
                 camera_type="phase_retrieval_camera",
                 camera_position=None,
                 pipeline=True,
                 filename="test_coron",
                 exposure_set_name=None,
                 **kwargs):
        """
        Takes a set of data with any camera, any DM command, any exposure time, etc.
        :param bias: (boolean) Apply a constant bias on the DM.
        :param flat_map: (boolean) Apply the flat map onto the DM.
        :param sine: (boolean) Apply a sine wave on the DM.
        :param exposure_time: (pint.quantity) Pint quantity for exposure time.
        :param num_exposures: (int) Number of exposures.
        :param step: (int) Step size to use for the motor positions (default is 10).
        :param path: (string) Path to save data.
        :param camera_type: (string) Camera type, maps to the [tested] section in the ini.
        :param position_list: (list) Postion(s) of the camera
        :param kwargs: Parameters for either the run_hicat_imaging function or the camera itself.
        """
        self.dm_command_object = dm_command_object
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.path = path
        self.image_type = image_type
        self.camera_type = camera_type
        self.camera_position = camera_position
        self.pipeline = pipeline
        self.filename = filename
        self.exposure_set_name = exposure_set_name
        self.kwargs = kwargs

    def experiment(self):
        take_exposures(self.dm_command_object,
                       self.exposure_time,
                       self.num_exposures,
                       self.path,
                       self.image_type,
                       self.camera_type,
                       self.camera_position,
                       self.pipeline,
                       self.filename,
                       self.exposure_set_name,
                       **self.kwargs)


def take_exposures(dm_command_object,
                   exposure_time,
                   num_exposures,
                   path,
                   image_type,
                   camera_type,
                   camera_position,
                   pipeline,
                   filename,
                   exposure_set_name,
                   **kwargs):
    # Wait to set the path until the experiment starts (rather than the constructor)
    if path is None:
        path = util.create_data_path(suffix="{}_data".format(filename))

    # Get the selected camera's current focus from the ini.
    motor_name = testbed.get_camera_motor_name(camera_type)
    focus_value = CONFIG_INI.getfloat(motor_name, "nominal")

    # Create the position list centered at the focus value, with constant step increments.
    if camera_position is None:
        camera_position = focus_value

    # Establish image type and set the FPM position and laser current
    if image_type == "coron":
        fpm_position = FpmPosition.coron
        laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "coron_current")
    elif image_type == "direct":
        fpm_position = FpmPosition.direct
        laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")

    # Take data
    with testbed.laser_source() as laser:
        laser.set_current(laser_current)

        with testbed.motor_controller():
            # Initialize motors.
            print("Initialized motors once, and will now only move the camera motor.")

        with testbed.dm_controller() as dm:
            dm.apply_shape(dm_command_object, dm_command_object.dm_num)

            if not camera_position:
                with testbed.motor_controller(initialize_to_nominal=True) as mc:
                    mc.absolute_move(testbed.get_camera_motor_name(camera_type), camera_position)
            metadata = MetaDataEntry("Camera Position", "CAM_POS", camera_position * 1000, "Position * 1000")

            testbed.run_hicat_imaging(exposure_time, num_exposures, fpm_position, path=path,
                                      filename=filename,
                                      exposure_set_name=exposure_set_name,
                                      extra_metadata=metadata,
                                      init_motors=False,
                                      camera_type=camera_type,
                                      pipeline=pipeline,
                                      **kwargs)
    return path
