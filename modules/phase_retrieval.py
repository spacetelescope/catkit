import numpy as np
import logging

from hicat.config import CONFIG_INI
from hicat.hardware import testbed
from hicat import util
from hicat.hardware.boston.commands import flat_command
from hicat.hicat_types import FpmPosition, MetaDataEntry


def take_phase_retrieval_data(exposure_time,
                              num_exposures,
                              step,
                              path,
                              camera_type,
                              position_list=None,
                              dm1_command=flat_command(False,True,dm_num=1),
                              dm2_command=flat_command(False,True,dm_num=2),
                              suffix=None,
                              **kwargs):

    util.setup_hicat_logging(path, "take_phase_retrieval_data")
    log = logging.getLogger(__name__)

    # Wait to set the path until the experiment starts (rather than the constructor)
    if path is None:
        suffix = "phase_retrieval_data" if suffix is None else "phase_retrieval_data_" + suffix
        path = util.create_data_path(suffix=suffix)

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
    log.debug("position list: " + str(position_list))

    with testbed.laser_source() as laser:
        direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
        laser.set_current(direct_laser_current)

        with testbed.motor_controller():
            # Initialize motors.
            log.info("Initialized motors once, and will now only move the camera motor.")

        with testbed.dm_controller() as dm:
            dm.apply_shape_to_both(dm1_command, dm2_command)

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
