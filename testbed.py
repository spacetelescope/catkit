from __future__ import (absolute_import, division,
                        unicode_literals)
# noinspection PyUnresolvedReferences
from builtins import *

import os
import logging
from glob import glob
import numpy as np
from astropy.io import fits

from ..hicat_types import LyotStopPosition, BeamDumpPosition, FpmPosition, quantity, ImageCentering
from . import testbed_state
from .. import data_pipeline
from .. import util
from .. import wolfram_wrappers
from ..config import CONFIG_INI

if not testbed_state.simulation:
    # Don't try to import the hardware drivers if we are pre-configured into simulation
    # mode. This allows running the simulator on computers that don't have all the
    # necessary driver files installed.
    from ..hardware.SnmpUps import SnmpUps
    from ..hardware.boston.BostonDmController import BostonDmController
    from ..hardware.newport.NewportMotorController import NewportMotorController
    from ..hardware.zwo.ZwoCamera import ZwoCamera
    from .thorlabs.ThorlabsMFF101 import ThorlabsMFF101
    from .thorlabs.ThorlabsMCLS1 import ThorlabsMCLS1
    from .thorlabs.ThorlabsTSP01 import ThorlabsTSP01

from ..interfaces.DummyLaserSource import DummyLaserSource
from ..hardware.FilterWheelAssembly import FilterWheelAssembly


"""Contains shortcut methods to create control objects for the hardware used on the testbed."""


# Shortcuts to obtaining hardware control objects.
def imaging_camera():
    """
    Proper way to control the imaging camera. Using this function keeps the scripts future-proof.  Use the "with"
    keyword to take advantage of the built-in context manager for safely closing the camera.
    :return: An instance of the Camera.py interface.
    """
    camera_name = CONFIG_INI.get("testbed", "imaging_camera")
    if testbed_state.simulation:
        from .. import simulators
        return simulators.SimZwoCamera(camera_name)
    else:
        return ZwoCamera(camera_name)


def phase_retrieval_camera():
    """
    Proper way to control the imaging camera. Using this function keeps the scripts future-proof.  Use the "with"
    keyword to take advantage of the built-in context manager for safely closing the camera.
    :return: An instance of the Camera.py interface.
    """
    camera_name = CONFIG_INI.get("testbed", "phase_retrieval_camera")
    if testbed_state.simulation:
        from .. import simulators
        return simulators.SimZwoCamera(camera_name)
    else:
        return ZwoCamera(camera_name)


def pupil_camera():
    """
        Proper way to control the pupil camera. Using this function keeps the scripts future-proof.  Use the "with"
        keyword to take advantage of the built-in context manager for safely closing the camera.
        :return: An instance of the Camera.py interface.
        """
    camera_name = CONFIG_INI.get("testbed", "pupil_camera")
    if testbed_state.simulation:
        from .. import simulators
        return simulators.SimZwoCamera(camera_name)
    else:
        return ZwoCamera(camera_name)


def dm_controller():
    """
    Proper way to control the deformable mirror controller. Using this function keeps the scripts future-proof.
    Use the "with" keyword to take advantage of the built-in context manager for safely closing the connection.
    The controller gives you the ability to send shapes to both DMs, or just to one.  If only sending to one DM,
    the other DM will still get commanded to all zeros.
    :return: An instance of the DeformableMirrorController.py interface.
    """
    if testbed_state.simulation:
        from .. import simulators
        return simulators.SimBostonDmController("boston_kilo952")
    else:
        return BostonDmController("boston_kilo952")


def motor_controller(initialize_to_nominal=True, use_testbed_state=True):
    """
    Proper way to control the motor controller. Using this function keeps the scripts future-proof.
    Use the "with" keyword to take advantage of the built-in context manager for safely closing the connection.
    :return: An instance of the MotorController.py interface.
    """
    if testbed_state.simulation:
        from .. import simulators
        return simulators.SimNewportMotorController("newport_xps_q8",
                                  initialize_to_nominal=initialize_to_nominal,
                                  use_testbed_state=use_testbed_state)
    else:
         return NewportMotorController("newport_xps_q8",
                                  initialize_to_nominal=initialize_to_nominal,
                                  use_testbed_state=use_testbed_state)


def beam_dump():
    if testbed_state.simulation:
        from .. import simulators
        return simulators.SimThorlabsMFF101("thorlabs_mff101_1")
    else:
        return ThorlabsMFF101("thorlabs_mff101_1")


def temp_sensor():
    sensor_config_ini_key = "thorlabs_tsp01_1"
    if testbed_state.simulation:
        from .. import simulators
        return simulators.SimThorlabsTSP01(sensor_config_ini_key)
    else:
        return ThorlabsTSP01(sensor_config_ini_key)


def laser_source():
    laser_name = CONFIG_INI.get("testbed", "laser_source")
    use_dummy = CONFIG_INI.getboolean(laser_name, "use_dummy")
    if use_dummy:
        return DummyLaserSource("dummy")
    else:
        if testbed_state.simulation:
            from .. import simulators
            return simulators.SimThorlabsMCLS1(laser_name)
        else:
            return ThorlabsMCLS1(laser_name)


def backup_power():
    if testbed_state.simulation:
        from .. import simulators
        return simulators.SimSnmpUps("blue_ups")
    else:
        return SnmpUps("blue_ups")


def get_camera(camera_type):
    if camera_type == "imaging_camera":
        return imaging_camera()
    elif camera_type == "phase_retrieval_camera":
        return phase_retrieval_camera()
    elif camera_type == "pupil_camera":
        return pupil_camera()


def get_camera_motor_name(camera_type):
    if camera_type == "imaging_camera":
        return "motor_img_camera"
    elif camera_type == "phase_retrieval_camera":
        return "motor_phase_camera"


# Convenience functions.
def run_hicat_imaging_broadband(filter_set, *args, **kwargs):
    """
    Convenience function that cycles through a set of filter combos and produces an image cube.

    :param filter_set: Name of the set of filter combinations, should map to the ini (eg bb_direct_set)
    :return: If file_mode is trure: Path to data cube, otherwise it is a list of the outputs.
    """

    broadband_filter_combos = CONFIG_INI.get("light_source_assembly", filter_set).split(",")
    original_path = kwargs.get("path", None)
    with FilterWheelAssembly("light_source_assembly") as wheels:

        output_list = []
        for i, filter_combo in enumerate(broadband_filter_combos):
            wheels.set_filters(filter_combo)

            # Extend the path one level using the name of the filter_combo.
            if original_path is not None:
                filter_combo_path = os.path.join(original_path, filter_combo)
                kwargs["path"] = filter_combo_path

            output_list.append(run_hicat_imaging(*args, **kwargs))

    # Make data cube.
    if kwargs.get("pipeline", True) and kwargs.get("file_mode", True):
        cube_filename = os.path.join(original_path, "broadband_cube.fits")

        # Updated fits header for cube to have entries for each filter set (eg filters1, filters2).
        data = []
        header = None
        for i, path in enumerate(output_list):
            data.append(fits.getdata(path))
            new_header = fits.getheader(path)
            value = new_header["FILTERS"]
            if i == 0:
                header = new_header
                header.remove("FILTERS")
            header.append(("FILTERS" + str(i + 1), value))

        return util.write_fits(data, cube_filename, header=header)
    else:
        return output_list


def run_hicat_imaging(exposure_time, num_exposures, fpm_position, lyot_stop_position=LyotStopPosition.in_beam,
                      file_mode=True, raw_skip=0, path=None, exposure_set_name=None, filename=None,
                      take_background_exposures=True, use_background_cache=True,
                      pipeline=True, return_pipeline_metadata=False, centering=ImageCentering.auto,
                      auto_exposure_time=True, auto_exposure_mask_size=None,
                      simulator=True,
                      extra_metadata=None,
                      resume=False,
                      init_motors=True,
                      camera_type="imaging_camera",
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
    :param return_pipeline_metadata: List of MetaDataEntry items that includes additional pipeline info.
    :param centering: (ImageCentering) Mode pipeline will use to find the center of images and recenter them.
    :param auto_exposure_time: Flag to enable auto exposure time correction.
    :param auto_exposure_mask_size: Value in lambda / d units to use to create a circle mask for auto exposure.
    :param simulator: Flag to enable Mathematica simulator. Supported when file_mode=True.
    :param extra_metadata: List or single MetaDataEntry.
    :param resume: Very primitive way to try and resume an experiment. Skips exposures that already exist on disk.
    :param init_motors: (Boolean) True will initially move all motors to nominal, False will not.
    :param camera_type: (String) Tells us which camera to use, valid values are under [testbed] in the ini.
    :param kwargs: Extra keywords to be passed to the camera's take_exposures function.
    :return: Defaults returns the path of the final calibrated image provided by the data pipeline.
    """

    log = logging.getLogger()
    # Initialize all motors and move Focal Plane Mask and Lyot Stop (will skip if already in correct place).
    if init_motors:
        initialize_motors(fpm_position=fpm_position, lyot_stop_position=lyot_stop_position)
    else:
        move_fpm(fpm_position)
        move_lyot_stop(lyot_stop_position)


    # If light_source_assembly is in use, make sure we initialize to something reasonable.
    source_name = CONFIG_INI.get("testbed", "laser_source")
    if not testbed_state.filter_wheels and source_name == "light_source_assembly":
        with FilterWheelAssembly("light_source_assembly") as filter_wheels:
            if fpm_position == FpmPosition.coron:
                filter_wheels.set_filters("bb_640_coron")
            else:
                filter_wheels.set_filters("bb_640_direct")

    # Auto Exposure.
    if auto_exposure_time:
        camera_name = CONFIG_INI.get("testbed", camera_type)
        max_counts = CONFIG_INI.getint(camera_name, "max_counts")
        min_counts = CONFIG_INI.getint(camera_name, "min_counts")
        subarray_size = CONFIG_INI.getint(camera_name, "width")

        circle_mask = None
        if auto_exposure_mask_size:
            log.info("fpm position is " + fpm_position.name)
            if fpm_position == fpm_position.coron:
                circle_mask = util.create_psf_mask((subarray_size, subarray_size), auto_exposure_mask_size)
                log.info("using auto-expose circular mask, radius (lambda/d): " + str(auto_exposure_mask_size))
            else:
                circle_mask = None
                log.info("not using the circular mask in direct mode")

        exposure_time = auto_exp_time_no_shape(exposure_time,
                                               min_counts,
                                               max_counts,
                                               camera_type=camera_type,
                                               mask=circle_mask)

    # Fits directories and filenames.
    exp_path, raw_path, img_path, bg_path = None, None, None, None
    if file_mode:
        # Combine exposure set into filename.
        filename = "image" if filename is None else filename
        filename = "{}_{}".format(exposure_set_name if exposure_set_name is not None else fpm_position.name, filename)

        # Create the standard directory structure.
        exp_path = os.path.join(path, exposure_set_name if exposure_set_name is not None else fpm_position.name)
        raw_path = os.path.join(exp_path, "raw")
        img_path = os.path.join(raw_path, "images")
        bg_path = os.path.join(raw_path, "backgrounds")

    # Move beam dump out of beam and take images.
    move_beam_dump(BeamDumpPosition.out_of_beam)
    with get_camera(camera_type) as cam:

        # Take images.
        img_list, metadata = cam.take_exposures(exposure_time, num_exposures, file_mode=file_mode,
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
                log.warning("Warning: Turning off exposure cache feature because it is only supported with file_mode=True")
                use_background_cache = False
            if use_background_cache and raw_skip != 0:
                log.warning("Warning: Setting use_background_cache=False, cannot be used with raw_skip")
                use_background_cache = False

            if use_background_cache:
                bg_cache_path = testbed_state.check_background_cache(exposure_time, num_exposures)

                # Cache hit - populate the bg_list with the path to
                if bg_cache_path is not None:
                    log.info("Using cached background exposures: " + bg_cache_path)
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
                bg_list, bg_metadata = cam.take_exposures(exposure_time, num_exposures,
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
        cal_metadata = None
        if pipeline and file_mode and raw_skip == 0:
            # Output is the path to the cal file.
            final_output = data_pipeline.standard_file_pipeline(exp_path, centering=centering)

        if pipeline and raw_skip > 0:

            # Output is the path to the cal file.
            final_output = data_pipeline.data_pipeline(img_list, bg_list, centering, output_path=exp_path,
                                                       filename_root=filename, img_metadata=metadata,
                                                       bg_metadata=bg_metadata)
        elif pipeline and not file_mode:

            # Output is the numpy data for the cal file, and our metadata updated with centroid information.
            final_output, cal_metadata = data_pipeline.data_pipeline(img_list, bg_list, centering,
                                                                     img_metadata=metadata,
                                                                     return_metadata=True)

        # Export the DM Command itself as a fits file.
        if file_mode:
            if testbed_state.dm1_command_object:
                testbed_state.dm1_command_object.export_fits(exp_path)
            if testbed_state.dm2_command_object:
                testbed_state.dm2_command_object.export_fits(exp_path)

        # Store config.ini.
        if file_mode:
            util.save_ini(os.path.join(exp_path, "config"))

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
    log = logging.getLogger()
    """A safe method to move the beam dump."""
    in_beam = True if beam_dump_position.value == BeamDumpPosition.in_beam.value else False

    # Check the internal state of the beam dump before moving it.
    if testbed_state.background is None or (testbed_state.background != in_beam):
        with beam_dump() as bd:
            log.info("Moving beam dump " + beam_dump_position.name)
            if beam_dump_position.value == BeamDumpPosition.in_beam.value:
                bd.move_to_position1()
            elif beam_dump_position.value == BeamDumpPosition.out_of_beam.value:
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
    if fpm_position.value == FpmPosition.coron.value:
        new_position = CONFIG_INI.getfloat("motor_FPM_Y", "default_coron")
    elif fpm_position.value == FpmPosition.direct.value:
        new_position = CONFIG_INI.getfloat("motor_FPM_Y", "direct")
    else:
        raise AttributeError("Unknown FpmPosition value: " + str(fpm_position))
    return new_position


def __get_lyot_position_from_ini(lyot_position):
    if lyot_position.value == LyotStopPosition.in_beam.value:
        new_position = CONFIG_INI.getfloat("motor_lyot_stop_x", "in_beam")
    elif lyot_position.value == LyotStopPosition.out_of_beam.value:
        new_position = CONFIG_INI.getfloat("motor_lyot_stop_x", "out_of_beam")
    else:
        raise AttributeError("Unknown LyotStopPosition value " + str(lyot_position))
    return new_position


def __get_max_pixel_count(data, mask=None):
    return np.max(data) if mask is None else np.max(data[np.nonzero(mask)])


def auto_exp_time_no_shape(start_exp_time, min_counts, max_counts, num_tries=50, mask=None,
                           camera_type="imaging_camera", centering=ImageCentering.auto, pipeline=False):
    """
    To be used when the dm shape is already applied. Uses the imaging camera to find the correct exposure time.
    :param start_exp_time: The initial time to begin testing with.
    :param min_counts: The minimum number of acceptable counts in the image.
    :param max_counts: The maximum number of acceptable counts in the image.
    :param num_tries: Safety mechanism to prevent infinite loops, max tries before giving up.
    :param mask: A mask for which to search for the max pixel (ie dark zone).
    :param camera_type: String value from ini under the [testbed] tag.
    :param centering: Mode from ImageCentering enum for how to center images.
    :param pipeline: Boolean for whether to use the pipeline or not.
    :return: The correct exposure time to use, or in the failure case, the start exposure time passed in.
    """
    log = logging.getLogger()
    move_beam_dump(BeamDumpPosition.out_of_beam)
    with get_camera(camera_type) as img_cam:

        # Take images and backgrounds and run them through the pipeline.
        if pipeline:
            img_list = img_cam.take_exposures(start_exp_time, 2, file_mode=False)
            move_beam_dump(BeamDumpPosition.in_beam)
            bg_list = img_cam.take_exposures(start_exp_time, 2, file_mode=False)
            image = data_pipeline.data_pipeline(img_list, bg_list, centering=centering)
        else:
            img_list = img_cam.take_exposures(start_exp_time, 1, file_mode=False)
            image = img_list[0]
        img_max = __get_max_pixel_count(image, mask=mask)

        # Hack to use the same pint registry across processes.
        upper_bound = quantity(start_exp_time.m, start_exp_time.u)
        lower_bound = quantity(0, upper_bound.u)
        log.info("Starting exposure time calibration...")

        if min_counts <= img_max <= max_counts:
            log.info("\tExposure time " + str(start_exp_time) + " yields " + str(img_max) + " counts ")
            log.info("\tReturning exposure time " + str(start_exp_time))
            return start_exp_time

        best = start_exp_time
        while img_max < max_counts:
            upper_bound *= 2
            move_beam_dump(BeamDumpPosition.out_of_beam)
            if pipeline:
                img_list = img_cam.take_exposures(round(upper_bound, 3), 2, file_mode=False)
                move_beam_dump(BeamDumpPosition.in_beam)
                bg_list = img_cam.take_exposures(round(upper_bound, 3), 2, file_mode=False)
                image = data_pipeline.data_pipeline(img_list, bg_list, centering=centering)
            else:
                img_list = img_cam.take_exposures(round(upper_bound, 3), 1, file_mode=False)
                image = img_list[0]
            img_max = __get_max_pixel_count(image, mask=mask)


            log.info("\tExposure time " + str(upper_bound) + " yields " + str(img_max) + " counts ")

        for i in range(num_tries):
            test = .5 * (upper_bound + lower_bound)
            move_beam_dump(BeamDumpPosition.out_of_beam)
            if pipeline:
                img_list = img_cam.take_exposures(round(test, 3), 2, file_mode=False)
                move_beam_dump(BeamDumpPosition.in_beam)
                bg_list = img_cam.take_exposures(round(test, 3), 2, file_mode=False)
                image = data_pipeline.data_pipeline(img_list, bg_list, centering=centering)
            else:
                img_list = img_cam.take_exposures(round(test, 3), 1, file_mode=False)
                image = img_list[0]
            img_max = __get_max_pixel_count(image, mask=mask)

            log.info("\tExposure time " + str(test) + " yields " + str(img_max) + " counts ")

            if min_counts <= img_max <= max_counts:
                log.info("\tReturning exposure time " + str(test))
                return test

            if img_max < min_counts:
                log.info("\tNew lower bound " + str(test))
                lower_bound = test
            elif img_max > max_counts:
                log.info("\tNew upper bound " + str(test))
                upper_bound = test
            best = test
        # If we run out of tries, return the best so far.
        return best
