import numpy as np
from .. import units, quantity
from ..newport.NewportMotorController import NewportMotorController
from ..zwo.ZwoCamera import ZwoCamera
from ..boston.BostonDmController import BostonDmController
from ..config import CONFIG_INI
from .thorlabs.ThorlabsMFF101 import ThorlabsMFF101

"""Contains shortcut methods to create control objects for the hardware used on the testbed."""


# Shortcuts to obtaining hardware control objects.
def imaging_camera():
    """
    Proper way to control the imaging camera. Using this function keeps the scripts future-proof.  Use the "with"
    keyword to take advantage of the built-in context manager for safely closing the camera.
    :return: An instance of the Camera.py interface. 
    """
    return ZwoCamera("zwo_ASI1600MM")


def dm_controller():
    """
    Proper way to control the deformable mirror controller. Using this function keeps the scripts future-proof.  
    Use the "with" keyword to take advantage of the built-in context manager for safely closing the connection.
    The controller gives you the ability to send shapes to both DMs, or just to one.  If only sending to one DM, 
    the other DM will still get commanded to all zeros.
    :return: An instance of the DeformableMirrorController.py interface. 
    """
    return BostonDmController("boston_kilo952")


def motor_controller():
    """
    Proper way to control the motor controller. Using this function keeps the scripts future-proof.
    Use the "with" keyword to take advantage of the built-in context manager for safely closing the connection.
    :return: An instance of the MotorController.py interface.
    """
    return NewportMotorController("newport_xps_q8")


def beam_dump():
    return ThorlabsMFF101("thorlabs_mff101_1")


# Convenience functions.
def apply_beam_dump():
    """A safe method to move the beam dump into the light path."""
    with beam_dump() as bd:
        bd.move_to_position1()


def remove_beam_dump():
    """A safe method to move the beam dump out of the light path."""
    with beam_dump() as bd:
        bd.move_to_position2()


def move_fpm_coron():
    """A safe method to move the focal plane mask into place."""
    motor_id = "motor_FPM_Y"
    coron_position = CONFIG_INI.getfloat(motor_id, "coron")

    with motor_controller() as mc:
        current_position = mc.get_position(motor_id)
        if coron_position != current_position:
            mc.absolute_move(motor_id, coron_position)


def move_fpm_direct():
    motor_id = "motor_FPM_Y"
    direct_position = CONFIG_INI.getfloat(motor_id, "direct")

    with motor_controller() as mc:
        current_position = mc.get_position(motor_id)
        if direct_position != current_position:
            mc.absolute_move(motor_id, direct_position)


def auto_exp_time(dm_shape, dm_num, start_exp_time, min_counts, max_counts, step, num_tries=10):
    """
    Applies a shape to the DM and uses the imaging camera to find the correct exposure time. 
    :param dm_shape: Numpy array of data to be used to command the dm.
    :param dm_num:  Which DM to send command to (1 or 2).
    :param start_exp_time: The initial time to begin testing with.
    :param min_counts: The minimum number of acceptable counts in the image.
    :param max_counts: The maximum number of acceptable counts in the image.
    :param step: The time increment to be used as a trial and error when the counts are out of range.
    :param num_tries: Safety mechanism to prevent infinite loops, max tries before giving up.  
    :return: The correct exposure time to use, or in the failure case, the start exposure time passed in.
    """

    with dm_controller() as dm:
        dm.apply_shape(dm_shape, dm_num)

        with imaging_camera() as img_cam:
            exp_time = start_exp_time
            print("Starting exposure time calibration...")
            for i in range(num_tries):

                img_list = img_cam.take_exposures_data(exp_time, 1)
                img_max = np.max(img_list[0])
                print("\tExposure time " + str(exp_time) + " yields " + str(img_max) + " counts ")

                if img_max < min_counts:
                    exp_time += step
                    print("\tAdjusted exposure time up to", exp_time)
                elif img_max > max_counts:
                    exp_time -= step
                    print("\tAdjusted exposure time down to", exp_time)

                    if exp_time < 0:
                        print("\tExposure time went negative, use a smaller step. Returning start time.")
                        return start_exp_time

                else:
                    print("\tReturning exposure time ", exp_time)
                    return exp_time

    print("\tUnable to auto calibrate exposure time, returning start time")
    return start_exp_time


def auto_exp_time_no_shape(start_exp_time, min_counts, max_counts, step, num_tries=10):
    """
    Applies a shape to the DM and uses the imaging camera to find the correct exposure time.
    :param dm_shape: Numpy array of data to be used to command the dm.
    :param dm_num:  Which DM to send command to (1 or 2).
    :param start_exp_time: The initial time to begin testing with.
    :param min_counts: The minimum number of acceptable counts in the image.
    :param max_counts: The maximum number of acceptable counts in the image.
    :param step: The time increment to be used as a trial and error when the counts are out of range.
    :param num_tries: Safety mechanism to prevent infinite loops, max tries before giving up.
    :return: The correct exposure time to use, or in the failure case, the start exposure time passed in.
    """
    with imaging_camera() as img_cam:
        exp_time = start_exp_time
        print("Starting exposure time calibration...")
        for i in range(num_tries):

            img_list = img_cam.take_exposures_data(exp_time, 1)
            img_max = np.max(img_list[0])
            print("\tExposure time " + str(exp_time) + " yields " + str(img_max) + " counts ")

            if img_max < min_counts:
                exp_time += step
                print("\tAdjusted exposure time up to", exp_time)
            elif img_max > max_counts:
                exp_time -= step
                print("\tAdjusted exposure time down to", exp_time)

                if exp_time < quantity(0, units.seconds):
                    print("\tExposure time went negative, use a smaller step. Returning start time.")
                    return start_exp_time

            else:
                print("\tReturning exposure time ", exp_time)
                return exp_time

    print("\tUnable to auto calibrate exposure time, returning start time")
    return start_exp_time