from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import os
from astropy.io import fits
from glob import glob

from hicat.hicat_types import ImageCentering
from ...hardware.boston.commands import flat_command
from ...hardware.boston.sin_command import sin_command
from ...hardware import testbed
from ...util import write_fits, read_fits
from ...hicat_types import LyotStopPosition, SinSpecification, quantity, units


positive_sin_dirname = "positive_sin"
negative_sin_dirname = "negative_sin"
flat_dirname = "flat"


def remove_crossterm(positive_sin, negative_sin, flat, output_path=None, output_header=None,
                     filename="sin_noxterm.fits"):
    clean_speckles = (positive_sin + negative_sin) / 2.0 - flat
    if output_path is not None:
        return write_fits(clean_speckles, os.path.join(output_path, filename), header=output_header)
    else:
        return clean_speckles


def __remove_crossterm_files(root_path, simulator=True):
    # Set up paths.
    positive_sin_path = glob(os.path.join(root_path, positive_sin_dirname, "*_cal.fits"))[0]
    negative_sin_path = glob(os.path.join(root_path, negative_sin_dirname, "*_cal.fits"))[0]
    flat_path = glob(os.path.join(root_path, flat_dirname, "*_cal.fits"))[0]

    # Open files.
    positive_sin_header, postive_sin_fits = read_fits(positive_sin_path)
    negative_sin_fits = read_fits(negative_sin_path, return_header=False)
    flat_fits = read_fits(flat_path, return_header=False)

    # Perform calculation  (postive + negative) / 2 - flat.
    remove_crossterm(postive_sin_fits,
                     negative_sin_fits,
                     flat_fits,
                     output_path=root_path,
                     output_header=positive_sin_header)

    if simulator:
        # Also apply to the simulated images.
        sim_positive_sin_path = glob(os.path.join(root_path, positive_sin_dirname, "simulated", "*.fits"))[0]
        sim_negative_sin_path = glob(os.path.join(root_path, negative_sin_dirname, "simulated", "*.fits"))[0]
        sim_flat_path = glob(os.path.join(root_path, flat_dirname, "simulated", "*.fits"))[0]

        # Open files.
        postive_simulator_fits = read_fits(sim_positive_sin_path, return_header=False)
        negative_simulator_fits = read_fits(sim_negative_sin_path, return_header=False)
        flat_simulator_fits = read_fits(sim_flat_path, return_header=False)

        remove_crossterm(postive_simulator_fits,
                         negative_simulator_fits,
                         flat_simulator_fits,
                         output_path=root_path,
                         output_header=positive_sin_header,
                         filename="sin_noxterm_simulated.fits")


def double_sin_remove_crossterm(sin_specification, alignment_speckle, bias, flat_map,
                                exposure_time, num_exposures, fpm_position,
                                auto_exposure_mask_size,
                                lyot_stop_position=LyotStopPosition.in_beam,
                                file_mode=True, raw_skip=0, path=None, simulator=True,
                                auto_exposure_time=True,
                                resume=False, centering=ImageCentering.auto,
                                dm=1, opposite=False,
                                **kwargs):
    """
    Takes 3 sets of exposures: "Positive Sin", "Negative Sin", and "Flat", and remove the cross term.
    If file_mode = True, then the final result will be saved as sin_noxterm.fits at specified path.  Otherwise
    the numpy image data will be returned by this function.
    :param sin_specification: (SinSpecification) for the sin wave to apply on the DM.
    :param alignment_speckle: (Boolean) Flag for whether to inject a speckle specifically for aligning images.
    :param bias: (Boolean) Apply a constant bias.
    :param flat_map: (Boolean) Apply the flat map.
    :param exposure_time: (Pint Quantity) Exposure time used for each exposure.
    :param num_exposures: (int) Number of raw exposures to take
    :param fpm_position: (FpmPosition) Coronograph position.
    :param auto_exposure_mask_size: (int) Value in lambda / d units to use to create a circle mask for auto exposure.
    :param lyot_stop_position: (LyotStopPosition) Lyot Stop position.
    :param file_mode: (Boolean) True will save fits files to disk, False will keep everything in memory.
    :param raw_skip: (int) Optimization for filemode=True that will skip writing x exposures for every 1 taken.
    :param path: (string) Root path to save all files.
    :param simulator: (Boolean) True will run the simulator (file_mode=True is required).
    :param auto_exposure_time: (Boolean) True will alter exposure time to get the counts into a linear range.
    :param resume: (Boolean) Primitive way to resume an experiment that was incomplete, file_mode=True only.
    :param centering: (ImageCentering) Mode pipeline will use to find the center of images and recenter them.
    :param kwargs: Specific keyword arguments passed to the Camera interface.
    :param dm: Which DM to apply the sine to? Either 1 or 2. The other will be set to flat.
    :param opposite: Bool; if true then put opposite amplitude sines on both DMs.
    :return:
    If file_mode=False: Numpy image data for final image with crossterm removed.
    If file_mode=True: Nothing is returned.
    """

    dm_to_control = dm
    dm_to_flatten = 2 if dm==1 else 1

    # Aligment speckle specification, only used when alignment_speckle param is True.
    alignment_speckle_spec = SinSpecification(90, 17, quantity(60, units.nanometer), 90)

    # Create positive sin wave from specification.
    positive_sine_spec_list = [sin_specification]
    if alignment_speckle:
        positive_sine_spec_list.append(alignment_speckle_spec)
    sin_command_object, sin_file_name = sin_command(positive_sine_spec_list, bias=bias, flat_map=flat_map,
                                                    return_shortname=True)

    # Create a "negative" sine wave by adding a phase of 180 from the original.
    negative_sine_spec_list = [SinSpecification(sin_specification.angle, sin_specification.ncycles,
                                                sin_specification.peak_to_valley, 180)]
    if alignment_speckle:
        negative_sine_spec_list.append(alignment_speckle_spec)
    negative_sin_command_object, neg_file_name = sin_command(negative_sine_spec_list, bias=bias, flat_map=flat_map,
                                                             return_shortname=True)

    # Create a flat dm command.
    if alignment_speckle:
        flat_command_object, flat_file_name = sin_command(alignment_speckle_spec, bias=bias, flat_map=flat_map,
                                                      return_shortname=True)
    else:
        flat_command_object, flat_file_name = flat_command(bias=bias, flat_map=flat_map, return_shortname=True)

    # Connect to the DM.
    with testbed.dm_controller() as dm:

        # Apply a flat to DM2.
        dm.apply_shape(flat_command(flat_map=True, dm_num=2), dm_to_flatten)

        # Positive sin wave.
        dm.apply_shape(sin_command_object, dm_to_control)
        if opposite:
            dm.apply_shape(negative_sin_command_object, dm_to_flatten)
        positive_final = testbed.run_hicat_imaging(exposure_time, num_exposures, fpm_position,
                                                   lyot_stop_position=lyot_stop_position,
                                                   file_mode=file_mode, raw_skip=raw_skip, path=path,
                                                   exposure_set_name=positive_sin_dirname,
                                                   filename=sin_file_name, auto_exposure_time=auto_exposure_time,
                                                   simulator=simulator, centering=centering,
                                                   auto_exposure_mask_size=auto_exposure_mask_size,
                                                   resume=resume, **kwargs)

        # Negative.
        dm.apply_shape(negative_sin_command_object, dm_to_control)
        if opposite:
            dm.apply_shape(sin_command_object, dm_to_flatten)
        negative_final = testbed.run_hicat_imaging(exposure_time, num_exposures, fpm_position,
                                                   lyot_stop_position=lyot_stop_position,
                                                   file_mode=file_mode, raw_skip=raw_skip, path=path,
                                                   exposure_set_name=negative_sin_dirname,
                                                   filename=sin_file_name, auto_exposure_time=auto_exposure_time,
                                                   simulator=simulator, centering=centering,
                                                   auto_exposure_mask_size=auto_exposure_mask_size,
                                                   resume=resume, **kwargs)

        # Flat (always use PSF image centering).
        dm.apply_shape(flat_command_object, dm_to_control)
        if opposite:
            dm.apply_shape(flat_command_object, dm_to_flatten)

        flat_final = testbed.run_hicat_imaging(exposure_time, num_exposures, fpm_position,
                                               lyot_stop_position=lyot_stop_position,
                                               file_mode=file_mode, raw_skip=raw_skip, path=path,
                                               exposure_set_name=flat_dirname,
                                               filename=sin_file_name, auto_exposure_time=auto_exposure_time,
                                               simulator=simulator, centering=centering,
                                               auto_exposure_mask_size=auto_exposure_mask_size,
                                               resume=resume, **kwargs)

    # Create the final file from adding speckles and subtracting the flat.
    if file_mode:
        __remove_crossterm_files(path, simulator=simulator)
    else:
        return remove_crossterm(positive_final, negative_final, flat_final)
