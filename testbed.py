from __future__ import (absolute_import, division,
                        print_function, unicode_literals)
# noinspection PyUnresolvedReferences
from builtins import *

import os
from glob import glob
import numpy as np

from . import testbed_state
from .thorlabs.ThorlabsMFF101 import ThorlabsMFF101
from .. import data_pipeline
from .. import util
from .. import wolfram_wrappers
from ..config import CONFIG_INI
from ..hardware.SnmpUps import SnmpUps
from ..hardware.boston.BostonDmController import BostonDmController
from ..hardware.newport.NewportMotorController import NewportMotorController
from ..hardware.thorlabs.ThorlabsMCLS1 import ThorlabsMLCS1
from ..hardware.zwo.ZwoCamera import ZwoCamera
from ..hicat_types import LyotStopPosition, BeamDumpPosition, FpmPosition, quantity
from ..interfaces.DummyLaserSource import DummyLaserSource

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


def motor_controller(initialize_to_nominal=True):
    """
    Proper way to control the motor controller. Using this function keeps the scripts future-proof.
    Use the "with" keyword to take advantage of the built-in context manager for safely closing the connection.
    :return: An instance of the MotorController.py interface.
    """
    return NewportMotorController("newport_xps_q8", initialize_to_nominal=initialize_to_nominal)


def beam_dump():
    return ThorlabsMFF101("thorlabs_mff101_1")


def laser_source():
    #return ThorlabsMLCS1("thorlabs_source_mcls1")
    return DummyLaserSource("dummy")


def backup_power():
    return SnmpUps("white_ups")


# Convenience functions.
def run_hicat_imaging(exposure_time, num_exposures, fpm_position, lyot_stop_position=LyotStopPosition.in_beam,
                      file_mode=True, raw_skip=0, path=None, exposure_set_name=None, filename=None,
                      take_background_exposures=True, use_background_cache=True,
                      pipeline=True, pipeline_plot=False, return_pipeline_metadata=False,
                      auto_exposure_time=True,
                      simulator=True,
                      extra_metadata=None,
                      resume=False,
                      **kwargs):
    """
    Standard function for taking imaging data with HiCAT.  For writing fits files (file_mode=True), 'path',
    'exposure_set_name' and 'filename' parameters are required.

    file_mode = True: (Default)
        - Returns the output of the pipeline, which will be a path to final calibrated fits file.
        - When pipeline=False, returns list of paths for images and  backgrounds (if take_background_exposures=True).
        - Simulator expects the output from the pipeline, so it will not work if pipeline=False.

    file_mode = False:
        - Returns the output of the pipeline, which is the data for the final calibrated image.
            - When return_pipeline_metadata=True, returns a second argument with metadata containing centroid info.
        - When pipeline=False, returns list of data for images and  backgrounds (if take_background_exposures=True).
        - Simulator, Background Cache, and Resume are not supported.

    :param exposure_time: Pint quantity for exposure time, otherwise in microseconds.
    :param num_exposures: Number of exposures.
    :param fpm_position: (hicat_types.FpmPosition) Position the focal plane mask will get moved to.
    :param lyot_stop_position: (hicat_types.LyotStopPosition) Position the lyot stop will get moved to.
    :param file_mode: If false the numpy data will be returned, if true fits files will be written to disk.
    :param raw_skip: Skips x images for every one taken, when used images will be stored in memory and returned.
    :param path: Path of the directory to save fits file to, required if file_mode is true.
    :param exposure_set_name: Additional directory level (ex: coron, direct).
    :param filename: Name for file, required if file_mode is true.
    :param take_background_exposures: Boolean flag for whether to take background exposures.
    :param use_background_cache: Reuses backgrounds with the same exposure time. Supported when file_mode=True.
    :param pipeline: True runs pipeline, False does not.  Inherits file_mode to determine whether to write final fits.
    :param pipeline_plot: Used for viewing the calibrated images as they are taken (usually for debugging).
    :param return_pipeline_metadata: List of MetaDataEntry items that includes additional pipeline info.
    :param auto_exposure_time: Flag to enable auto exposure time correction.
    :param simulator: Flag to enable Mathematica simulator. Supported when file_mode=True.
    :param extra_metadata: List or single MetaDataEntry.
    :param resume: Very primitive way to try and resume an experiment. Skips exposures that already exist on disk.
    :param kwargs: Extra keywords to be passed to the camera's take_exposures function.
    :return: Defaults returns the path of the final calibrated image provided by the data pipeline.
    """

    # Initialize all motors and move Focal Plane Mask and Lyot Stop (will skip if already in correct place).
    initialize_motors(fpm_position=fpm_position, lyot_stop_position=lyot_stop_position)

    # Auto Exposure.
    if auto_exposure_time:
        min_counts = CONFIG_INI.getint("zwo_ASI1600MM", "min_counts")
        max_counts = CONFIG_INI.getint("zwo_ASI1600MM", "max_counts")
        exposure_time = auto_exp_time_no_shape(exposure_time, min_counts, max_counts)

    # Fits directories and filenames.
    exp_path, raw_path, img_path, bg_path = None, None, None, None
    if file_mode:

        # Combine exposure set into filename.
        filename = "{}_{}".format(exposure_set_name, filename)

        # Create the standard directory structure.
        exp_path = os.path.join(path, exposure_set_name)
        raw_path = os.path.join(exp_path, "raw")
        img_path = os.path.join(raw_path, "images")
        bg_path = os.path.join(raw_path, "backgrounds")

    # Move beam dump out of beam and take images.
    move_beam_dump(BeamDumpPosition.out_of_beam)
    with imaging_camera() as img_cam:

        # Take images.
        img_list, metadata = img_cam.take_exposures(exposure_time, num_exposures, file_mode=file_mode,
                                                    raw_skip=raw_skip, path=img_path, filename=filename,
                                                    extra_metadata=extra_metadata,
                                                    return_metadata=True,
                                                    resume=resume,
                                                    **kwargs)

        # Background images.
        bg_list = []
        bg_metadata = None
        if take_background_exposures:
            if use_background_cache and not file_mode:
                print("Warning: Turning off exposure cache feature because it is only supported with file_mode=True")
                use_background_cache = False
            if use_background_cache and raw_skip != 0:
                print("Warning: Setting use_background_cache=False, cannot be used with raw_skip")
                use_background_cache = False

            if use_background_cache:
                bg_cache_path = testbed_state.check_background_cache(exposure_time, num_exposures)

                # Cache hit - populate the bg_list with the path to
                if bg_cache_path is not None:
                    print("Using cached background exposures: " + bg_cache_path)
                    bg_list = glob(os.path.join(bg_cache_path, "*.fits"))

                    # Leave a small text file in background directory that points to real exposures.
                    os.makedirs(bg_path)
                    cache_file_path = os.path.join(bg_path, "cache_directory.txt")

                    with open(cache_file_path, mode=b'w') as cache_file:
                        cache_file.write(bg_cache_path)
            if not bg_list:
                # Move the beam dump in the path and take background exposures.
                move_beam_dump(BeamDumpPosition.in_beam)
                bg_filename = "bkg_" + filename if file_mode else None
                bg_list, bg_metadata = img_cam.take_exposures(exposure_time, num_exposures,
                                                              file_mode=file_mode,
                                                              path=bg_path, filename=bg_filename, raw_skip=raw_skip,
                                                              extra_metadata=extra_metadata,
                                                              resume=resume,
                                                              return_metadata=True,
                                                              **kwargs)
                if use_background_cache:
                    testbed_state.add_background_to_cache(exposure_time, num_exposures, bg_path)

        # Run data pipeline
        final_output = None
        satellite_spots = True if fpm_position == FpmPosition.coron else False
        cal_metadata = None
        if pipeline and file_mode and raw_skip == 0:

            # Output is the path to the cal file.
            final_output = data_pipeline.standard_file_pipeline(exp_path)

        if pipeline and raw_skip > 0:

            # Output is the path to the cal file.
            final_output = data_pipeline.data_pipeline(img_list, bg_list, satellite_spots, output_path=exp_path,
                                                       filename_root=filename, img_metadata=metadata,
                                                       bg_metadata=bg_metadata)
        elif pipeline and not file_mode:

            # Output is the numpy data for the cal file, and our metadata updated with centroid information.
            final_output, cal_metadata = data_pipeline.data_pipeline(img_list, bg_list, satellite_spots,
                                                                     plot=pipeline_plot, img_metadata=metadata,
                                                                     return_metadata=True)

        # Export the DM Command itself as a fits file.
        if file_mode:
            testbed_state.dm1_command_object.export_fits(os.path.join(path, exposure_set_name))

        # Store config.ini.
        if file_mode:
            util.save_ini(os.path.join(path, "config"))

        # Simulator (file-based only).
        if file_mode and simulator:
            wolfram_wrappers.run_simulator(os.path.join(path, exposure_set_name), filename + ".fits", fpm_position.name)

        # When the pipeline is off, return image lists (data or path depending on filemode).
        if not pipeline:
            if take_background_exposures:
                return img_list, bg_list
            else:
                return img_list

        # Return the output of the pipeline and metadata (if requested).
        if return_pipeline_metadata:
            return final_output, cal_metadata
        else:
            return final_output


def move_beam_dump(beam_dump_position):
    """A safe method to move the beam dump."""
    in_beam = True if beam_dump_position == BeamDumpPosition.in_beam else False

    # Check the internal state of the beam dump before moving it.
    if testbed_state.background is None or (testbed_state.background != in_beam):
        with beam_dump() as bd:
            if beam_dump_position is BeamDumpPosition.in_beam:
                bd.move_to_position1()
            elif beam_dump_position is BeamDumpPosition.out_of_beam:
                bd.move_to_position2()


def initialize_motors(fpm_position=None, lyot_stop_position=None):
    with motor_controller() as mc:
        if fpm_position:
            mc.absolute_move("motor_FPM_Y", __get_fpm_position_from_ini(fpm_position))
        if lyot_stop_position:
            mc.absolute_move("motor_lyot_stop_x", __get_lyot_position_from_ini(lyot_stop_position))


def move_fpm(fpm_position):
    """A safe method to move the focal plane mask."""
    with motor_controller(initialize_to_nominal=False) as mc:
        motor_id = "motor_FPM_Y"
        new_position = __get_fpm_position_from_ini(fpm_position)
        mc.absolute_move(motor_id, new_position)


def move_lyot_stop(lyot_stop_position):
    """A safe method to move the lyot stop."""
    with motor_controller(initialize_to_nominal=False) as mc:
        motor_id = "motor_lyot_stop_x"
        new_position = __get_lyot_position_from_ini(lyot_stop_position)
        mc.absolute_move(motor_id, new_position)


def __get_fpm_position_from_ini(fpm_position):
    if fpm_position is FpmPosition.coron:
        new_position = CONFIG_INI.getfloat("motor_FPM_Y", "default_coron")
    else:
        new_position = CONFIG_INI.getfloat("motor_FPM_Y", "direct")
    return new_position


def __get_lyot_position_from_ini(lyot_position):
    if lyot_position is LyotStopPosition.in_beam:
        new_position = CONFIG_INI.getfloat("motor_lyot_stop_x", "in_beam")
    else:
        new_position = CONFIG_INI.getfloat("motor_lyot_stop_x", "out_of_beam")
    return new_position


def __get_max_pixel_count(data, mask=None):
    return np.max(data) if mask is None else np.max(data[np.nonzero(mask)])


def auto_exp_time_no_shape(start_exp_time, min_counts, max_counts, num_tries=50, mask=None):
    """
    To be used when the dm shape is already applied. Uses the imaging camera to find the correct exposure time.
    :param start_exp_time: The initial time to begin testing with.
    :param min_counts: The minimum number of acceptable counts in the image.
    :param max_counts: The maximum number of acceptable counts in the image.
    :param num_tries: Safety mechanism to prevent infinite loops, max tries before giving up.
    :param mask: A mask for which to search for the max pixel (ie dark zone).
    :return: The correct exposure time to use, or in the failure case, the start exposure time passed in.
    """
    move_beam_dump(BeamDumpPosition.out_of_beam)
    with imaging_camera() as img_cam:

        img_list = img_cam.take_exposures(start_exp_time, 1, file_mode=False)
        img_max = __get_max_pixel_count(img_list[0], mask=mask)

        # Hack to use the same pint registry across processes.
        upper_bound = quantity(start_exp_time.m, start_exp_time.u)
        lower_bound = quantity(0, upper_bound.u)
        print("Starting exposure time calibration...")

        if min_counts <= img_max <= max_counts:
            print("\tExposure time " + str(start_exp_time) + " yields " + str(img_max) + " counts ")
            print("\tReturning exposure time " + str(start_exp_time))
            return start_exp_time

        best = start_exp_time
        while img_max < max_counts:
            upper_bound *= 2
            img_list = img_cam.take_exposures(round(upper_bound, 3), 1, file_mode=False)
            img_max = __get_max_pixel_count(img_list[0], mask=mask)
            print("\tExposure time " + str(upper_bound) + " yields " + str(img_max) + " counts ")

        for i in range(num_tries):
            test = .5 * (upper_bound + lower_bound)
            img_list = img_cam.take_exposures(round(test, 3), 1, file_mode=False)
            img_max = __get_max_pixel_count(img_list[0], mask=mask)
            print("\tExposure time " + str(test) + " yields " + str(img_max) + " counts ")

            if min_counts <= img_max <= max_counts:
                print("\tReturning exposure time " + str(test))
                return test

            if img_max < min_counts:
                print("\tNew lower bound " + str(test))
                lower_bound = test
            elif img_max > max_counts:
                print("\tNew upper bound " + str(test))
                upper_bound = test
            best = test
        # If we run out of tries, return the best so far.
        return best
