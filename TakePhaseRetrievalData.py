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
from ..hardware.boston.flat_command import flat_command


class TakePhaseRetrievalData(Experiment):
    name = "Take Phase Retrieval Data"

    def __init__(self,
                 bias=False,
                 flat_map=True,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=5,
                 position_list=np.arange(-100, 110, step=10),
                 path=None,
                 camera_type="phase_retrieval_camera",
                 **kwargs):
        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.position_list = position_list
        self.path = path
        self.camera_type = camera_type
        self.kwargs = kwargs

    def experiment(self):
        take_phase_retrieval_data(self.bias,
                                  self.flat_map,
                                  self.exposure_time,
                                  self.num_exposures,
                                  self.position_list,
                                  self.path,
                                  self.camera_type,
                                  **self.kwargs)


def take_phase_retrieval_data(bias,
                              flat_map,
                              exposure_time,
                              num_exposures,
                              position_list,
                              path,
                              camera_type,
                              **kwargs):
    # Wait to set the path until the experiment starts (rather than the constructor)
    if path is None:
        path = util.create_data_path(suffix="phase_retrieval_data")

    # Get the selected camera's current focus from the ini.
    focus_value = CONFIG_INI.getfloat(testbed.get_camera_motor_name(camera_type), "nominal")

    with testbed.laser_source() as laser:
        direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
        laser.set_current(direct_laser_current)

        with testbed.motor_controller():
            # Initialize motors.
            print("Initialized motors once, and will now only move the camera motor.")

        with testbed.dm_controller() as dm:
            dm_command_object = flat_command(bias=bias, flat_map=flat_map)
            dm.apply_shape(dm_command_object, 1)

            for i, position in enumerate(position_list):
                with testbed.motor_controller(initialize_to_nominal=False) as mc:
                    mc.absolute_move(testbed.get_camera_motor_name(camera_type), position)
                from_focus = position - focus_value
                meta_cam_pos = MetaDataEntry("Camera Position", "CAM_POS", position * 1000, "Position * 1000")
                meta_from_focus = MetaDataEntry("From Focus", "DEFOCUS", from_focus, "Millimeters from focus")
                metadata = [meta_cam_pos, meta_from_focus]
                testbed.run_hicat_imaging(exposure_time, num_exposures, FpmPosition.direct, path=path,
                                          filename="phase_retrieval",
                                          exposure_set_name="from_focus_" + str(round(from_focus, 2)),
                                          extra_metadata=metadata,
                                          init_motors=False,
                                          camera_type=camera_type,
                                          **kwargs)
    return path
