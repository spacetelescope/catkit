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
                 step=10,
                 path=None,
                 camera_type="phase_retrieval_camera",
                 position_list = None,
                 **kwargs):
        """
        Takes a set of data with the phase_retrieval camera (default) at constant "step" increments from focus.
        :param bias: (boolean) Apply a constant bias on the DM.
        :param flat_map: (boolean) Apply the flat map onto the DM.
        :param exposure_time: (pint.quantity) Pint quantity for exposure time.
        :param num_exposures: (int) Number of exposures.
        :param step: (int) Step size to use for the motor positions (default is 10).
        :param path: (string) Path to save data.
        :param camera_type: (string) Camera type, maps to the [tested] section in the ini.
        :param kwargs: Parameters for either the run_hicat_imaging function or the camera itself.
        """
        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.step = step
        self.path = path
        self.camera_type = camera_type
        self.position_list = position_list
        self.kwargs = kwargs

    def experiment(self):
        take_phase_retrieval_data(self.bias,
                                  self.flat_map,
                                  self.exposure_time,
                                  self.num_exposures,
                                  self.step,
                                  self.path,
                                  self.camera_type,
                                  position_list = self.position_list,
                                  **self.kwargs)


def take_phase_retrieval_data(bias,
                              flat_map,
                              exposure_time,
                              num_exposures,
                              step,
                              path,
                              camera_type,
                              position_list=None,
                              **kwargs):
    # Wait to set the path until the experiment starts (rather than the constructor)
    if path is None:
        path = util.create_data_path(suffix="phase_retrieval_data")

    # Get the selected camera's current focus from the ini.
    motor_name = testbed.get_camera_motor_name(camera_type)
    focus_value = CONFIG_INI.getfloat(motor_name, "nominal")
    min_motor_position = CONFIG_INI.getint(motor_name, "min")
    max_motor_position = CONFIG_INI.getint(motor_name, "max")

    # Create the position list centered at the focus value, with constant step increments.
    if position_list is None:
        bottom_steps = np.arange(focus_value, min_motor_position, step=-step)
        top_steps = np.arange(focus_value + step, max_motor_position, step=step)
        position_list = bottom_steps.tolist()
        position_list.extend(top_steps.tolist())
        position_list = [round(elem, 2) for elem in position_list]
        position_list = sorted(position_list)
        position_list = sorted(position_list)
    print(position_list)

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
