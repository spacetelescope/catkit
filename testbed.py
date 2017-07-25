import numpy as np
import os

from enum import Enum

from .. import units, quantity
from ..newport.NewportMotorController import NewportMotorController
from ..zwo.ZwoCamera import ZwoCamera
from ..boston.BostonDmController import BostonDmController
from ..config import CONFIG_INI
from .. import util
from .thorlabs.ThorlabsMFF101 import ThorlabsMFF101
from .thorlabs.ThorlabsMCLS1 import ThorlabsMLCS1
from .. import data_pipeline


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


def laser_source():
    return ThorlabsMLCS1("thorlabs_source_mcls1")


# Convenience functions.
def run_hicat_imaging(dm_command_object, path, exposure_set_name, file_name, fpm_position, exposure_time, num_exposures,
                      simulator=True, pipeline=True, **kwargs):

    full_filename = "{}_{}".format(exposure_set_name, file_name)
    output = take_exposures_and_background(exposure_time, num_exposures, fpm_position, path, full_filename,
                                  exposure_set_name=exposure_set_name, pipeline=pipeline, **kwargs)
                                  
    # Export the DM Command itself as a fits file.
    dm_command_object.export_fits(os.path.join(path, exposure_set_name))

    # Store config.ini.
    util.save_ini(os.path.join(path,"config"))

    if simulator:
        util.run_simulator(os.path.join(path, exposure_set_name), full_filename + ".fits", fpm_position.name)

    return output


def take_exposures_and_background(exposure_time, num_exposures, fpm_position, path="", filename="", exposure_set_name="",
                                  fits_header_dict=None, center_x=None, center_y=None, width=None, height=None,
                                  gain=None, full_image=None, bins=None, resume=False, pipeline=True, write_out_data=True):
    """
    Standard way to take data on hicat.  This function takes exposures, background images, and then runs a data pipeline
    to average the images and remove bad pixels.  It controls the beam dump for you, no need to initialize it prior.
    """

    # Move the FPM to the desired position.
    move_fpm(fpm_position)

    # Create the standard directory structure.
    if write_out_data:
        raw_path = os.path.join(path, exposure_set_name, "raw")
        img_path = os.path.join(raw_path, "images")
        bg_path = os.path.join(raw_path, "backgrounds")

    else:
        raw_path = ""
        img_path = ""
        bg_path = ""

    with imaging_camera() as img_cam:

        # First take images.
        move_beam_dump(BeamDumpPosition.out_of_beam)
        img_list = img_cam.take_exposures(exposure_time, num_exposures, img_path, filename, fits_header_dict=fits_header_dict,
                                    center_x=center_x, center_y=center_y, width=width, height=height, gain=gain,
                                    full_image=full_image, bins=bins, resume=resume, write_out_data=write_out_data)

        # Now move the beam dump in the path and take backgrounds.
        move_beam_dump(BeamDumpPosition.in_beam)
        bg_filename = 'bkg_{}'.format(filename)
        bg_list = img_cam.take_exposures(exposure_time, num_exposures, bg_path, bg_filename, fits_header_dict=fits_header_dict,
                                    center_x=center_x, center_y=center_y, width=width, height=height, gain=gain,
                                    full_image=full_image, bins=bins, resume=resume, write_out_data=write_out_data)

        # Run data pipeline.
        if pipeline:
            if write_out_data:
                data_pipeline.run_data_pipeline(raw_path)
            else:
                calibrated = data_pipeline.calibration_pipeline(img_list,bg_list)
                return calibrated



def move_beam_dump(beam_dump_position):
    """A safe method to move the beam dump."""
    with beam_dump() as bd:
        if beam_dump_position is BeamDumpPosition.in_beam:
            bd.move_to_position1()
        elif beam_dump_position is BeamDumpPosition.out_of_beam:
            bd.move_to_position2()


def move_fpm(fpm_position):
    """A safe method to move the focal plane mask."""
    with motor_controller() as mc:
        motor_id = "motor_FPM_Y"

        if fpm_position is FpmPosition.coron:
            new_position = CONFIG_INI.getfloat(motor_id, "nominal")
        elif fpm_position is FpmPosition.direct:
            new_position =  CONFIG_INI.getfloat(motor_id, "direct")

        current_position = mc.get_position(motor_id)
        if new_position != current_position:
            mc.absolute_move(motor_id, new_position)


def auto_exp_time_no_shape(start_exp_time, min_counts, max_counts, num_tries=50):
    """
    To be used when the dm shape is already applied. Uses the imaging camera to find the correct exposure time.
    :param start_exp_time: The initial time to begin testing with.
    :param min_counts: The minimum number of acceptable counts in the image.
    :param max_counts: The maximum number of acceptable counts in the image.
    :param step: The time increment to be used as a trial and error when the counts are out of range.
    :param num_tries: Safety mechanism to prevent infinite loops, max tries before giving up.
    :return: The correct exposure time to use, or in the failure case, the start exposure time passed in.
    """

    with imaging_camera() as img_cam:

        img_list = img_cam.take_exposures_data(start_exp_time, 1)
        img_max = np.max(img_list[0])
        upper_bound = start_exp_time
        lower_bound = quantity(0, start_exp_time.u)
        print("Starting exposure time calibration...")

        if img_max >= min_counts and img_max <= max_counts:
            print("\tExposure time " + str(start_exp_time) + " yields " + str(img_max) + " counts ")
            print("\tReturning exposure time " + str(start_exp_time))
            return start_exp_time

        while(img_max < max_counts):
            upper_bound *= 2
            img_list = img_cam.take_exposures_data(upper_bound, 1)
            img_max = np.max(img_list[0])
            print("\tExposure time " + str(upper_bound) + " yields " + str(img_max) + " counts ")

        for i in range(num_tries):
            test = .5 * (upper_bound + lower_bound)
            img_list = img_cam.take_exposures_data(test, 1)
            img_max = np.max(img_list[0])
            print("\tExposure time " + str(test) + " yields " + str(img_max) + " counts ")

            if img_max >= min_counts and img_max <= max_counts:
                print("\tReturning exposure time " + str(test))
                return test

            if img_max < min_counts:
                print("\tNew lower bound " + str(test))
                lower_bound = test
            elif img_max > max_counts:
                print("\tNew upper bound " + str(test))
                upper_bound = test

class BeamDumpPosition(Enum):
    """
    Enum for the possible states of the Beam Dump.
    """
    in_beam = 1
    out_of_beam = 2


class FpmPosition(Enum):
    """
    Enum for the possible states for the focal plane mask.
    """
    coron = 1
    direct = 2
