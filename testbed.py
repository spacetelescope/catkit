from __future__ import (absolute_import, division,
                        print_function, unicode_literals)
# noinspection PyUnresolvedReferences
from builtins import *

import os
from glob import glob

import numpy as np

from . import testbed_state
from .SnmpUps import SnmpUps
from .thorlabs.ThorlabsMFF101 import ThorlabsMFF101
from .. import data_pipeline
from .. import quantity
from .. import util
from ..config import CONFIG_INI
from ..hardware.boston.BostonDmController import BostonDmController
from ..hardware.newport.NewportMotorController import NewportMotorController
from ..hicat_types import *
from ..hardware.thorlabs.ThorlabsMCLS1 import ThorlabsMLCS1
from ..hardware.zwo.ZwoCamera import ZwoCamera

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


def backup_power():
    return SnmpUps("white_ups")


# Convenience functions.
def run_hicat_imaging(exposure_time, num_exposures, fpm_position, lyot_stop_position=LyotStopPosition.in_beam,
                      write_raw_fits=True, raw_skip=0, path=None, exposure_set_name=None, filename=None,
                      take_background_exposures=True, use_background_cache=True,
                      pipeline_mode=PipeLineMode.output_fits,
                      auto_exposure_time=True,
                      simulator=True,
                      extra_metadata=None,
                      store_dm_command=True,
                      resume=False,
                      **camera_kwargs):
    """
    Standard function for taking imaging data with HiCAT.  For writing fits files, 'path', 'exposure_set_name' and
    'filename' parameters are required.
    :param exposure_time: Pint quantity for exposure time, otherwise in microseconds.
    :param num_exposures: Number of exposures.
    :param fpm_position:
    :param lyot_stop_position:
    :param write_raw_fits: If true fits file will be written to disk, otherwise the numpy data will be returned.
    :param raw_skip: Skips x images for every one taken, when used images will be stored in memory and returned.
    :param path: Path of the directory to save fits file to, required if write_raw_fits is true.
    :param exposure_set_name: Additional directory level (ex: coron, direct).
    :param filename: Name for file, required if write_raw_fits is true.
    :param take_background_exposures:
    :param use_background_cache: Reuses backgrounds with the same exposure time. Supported when write_raw_fits=True.
    :param pipeline_mode:
    :param auto_exposure_time:
    :param simulator:
    :param extra_metadata:
    :param store_dm_command:
    :param resume:
    :param camera_kwargs:
    :return: hicat_types.HicatImagingProducts object.
    """

    # Move Focal Plane Mask and Lyot Stop(will skip if already in correct place).
    move_fpm(fpm_position)
    move_lyot_stop(lyot_stop_position)

    # Auto Exposure.
    if auto_exposure_time:
        move_beam_dump(BeamDumpPosition.out_of_beam)
        min_counts = CONFIG_INI.getint("zwo_ASI1600MM", "min_counts")
        max_counts = CONFIG_INI.getint("zwo_ASI1600MM", "max_counts")
        exposure_time = auto_exp_time_no_shape(exposure_time, min_counts, max_counts)

    # Fits directories and filenames.
    raw_path, img_path, bg_path = None
    if write_raw_fits:

        # Combine exposure set into filename.
        filename = "{}_{}".format(exposure_set_name, filename)

        # Create the standard directory structure.
        raw_path = os.path.join(path, exposure_set_name, "raw")
        img_path = os.path.join(raw_path, "images")
        bg_path = os.path.join(raw_path, "backgrounds")

    # Output container.
    hicat_imaging_products = HicatImagingProducts()

    # Move beam dump out of beam and take images.
    move_beam_dump(BeamDumpPosition.out_of_beam)
    with imaging_camera() as img_cam:

        # Take images.
        img_list, metadata = img_cam.take_exposures(exposure_time, num_exposures, write_raw_fits=write_raw_fits,
                                                    raw_skip=raw_skip, path=img_path, filename=filename,
                                                    extra_metadata=extra_metadata,
                                                    resume=resume,
                                                    **camera_kwargs)
        # Add image paths or image data to output products.
        if write_raw_fits and raw_skip == 0:
            hicat_imaging_products.img_data = img_list
        else:
            hicat_imaging_products.img_paths = img_list

        # Background images.
        bg_list = []
        write_raw_fits_bg = write_raw_fits
        raw_skip_bg = raw_skip
        if take_background_exposures:
            if use_background_cache and not write_raw_fits:
                print("Warning: Setting write_raw_fits=True only for bg exposures to use background cache feature.")
                write_raw_fits_bg = True
            if use_background_cache and raw_skip != 0:
                print("Warning: Setting raw_skip=0 only for bg exposures to use background cache feature.")
                raw_skip_bg = 0

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
                bg_filename = "bkg_" + filename

                bg_list, bg_metadata = img_cam.take_exposures(exposure_time, num_exposures,
                                                              write_raw_fits=write_raw_fits_bg,
                                                              path=bg_path, filename=bg_filename, raw_skip=raw_skip_bg,
                                                              extra_metadata=extra_metadata,
                                                              resume=resume,
                                                              **camera_kwargs)
                hicat_imaging_products.bg_metadata = bg_metadata
                if use_background_cache:
                    testbed_state.add_background_to_cache(exposure_time, num_exposures, bg_path)

            # Add bg_list to output products as either bg_paths or bg_data.
            if write_raw_fits:
                hicat_imaging_products.bg_paths = bg_list
            else:
                hicat_imaging_products.bg_data = bg_list

        # Run data pipeline TODO: Incorporate additional metadata from pipeline into metadata output product.
        if pipeline_mode == PipeLineMode.output_fits:
            hicat_imaging_products.cal_path = data_pipeline.file_pipeline(raw_path, bg_list=bg_list)
        elif pipeline_mode == PipeLineMode.output_data:
            hicat_imaging_products.cal_data = data_pipeline.data_pipeline(img_list, bg_list)
        elif pipeline_mode == PipeLineMode.output_data_and_plot:
            hicat_imaging_products.cal_data = data_pipeline.data_pipeline(img_list, bg_list, plot=True)

        hicat_imaging_products.img_metadata = metadata

        # Export the DM Command itself as a fits file.
        if store_dm_command:
            testbed_state.dm1_command_object.export_fits(os.path.join(path, exposure_set_name))

        # Store config.ini.
        util.save_ini(os.path.join(path, "config"))

        if simulator:
            util.run_simulator(os.path.join(path, exposure_set_name), filename + ".fits", fpm_position.name)

        return hicat_imaging_products


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
        new_position = None

        if fpm_position is FpmPosition.coron:
            new_position = CONFIG_INI.getfloat(motor_id, "nominal")
        elif fpm_position is FpmPosition.direct:
            new_position = CONFIG_INI.getfloat(motor_id, "direct")

        current_position = mc.get_position(motor_id)
        if new_position != current_position:
            mc.absolute_move(motor_id, new_position)


def move_lyot_stop(lyot_stop_position):
    """A safe method to move the lyot stop."""
    with motor_controller() as mc:
        motor_id = "motor_lyot_stop_x"
        new_position = None

        if lyot_stop_position is LyotStopPosition.in_beam:
            new_position = CONFIG_INI.getfloat(motor_id, "in_beam")
        elif lyot_stop_position is LyotStopPosition.out_of_beam:
            new_position = CONFIG_INI.getfloat(motor_id, "out_of_beam")

        current_position = mc.get_position(motor_id)
        if new_position != current_position:
            mc.absolute_move(motor_id, new_position)


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

        img_list = img_cam.take_exposures(start_exp_time, 1, write_raw_fits=False)
        img_max = __get_max_pixel_count(img_list[0], mask=mask)

        upper_bound = start_exp_time
        lower_bound = quantity(0, start_exp_time.u)
        print("Starting exposure time calibration...")

        if min_counts <= img_max <= max_counts:
            print("\tExposure time " + str(start_exp_time) + " yields " + str(img_max) + " counts ")
            print("\tReturning exposure time " + str(start_exp_time))
            return start_exp_time

        best = start_exp_time
        while img_max < max_counts:
            upper_bound *= 2
            img_list = img_cam.take_exposures(upper_bound, 1, write_raw_fits=False)
            img_max = __get_max_pixel_count(img_list[0], mask=mask)
            print("\tExposure time " + str(upper_bound) + " yields " + str(img_max) + " counts ")

        for i in range(num_tries):
            test = .5 * (upper_bound + lower_bound)
            img_list = img_cam.take_exposures(test, 1, write_raw_fits=False)
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
