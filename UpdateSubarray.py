from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from astropy.stats.sigma_clipping import sigma_clipped_stats
from builtins import *
import logging
import os
from glob import glob
import numpy as np
from photutils.centroids.core import centroid_1dg, centroid_2dg

from photutils.detection.core import find_peaks

from .Experiment import Experiment
from ..hicat_types import *
from ..hardware.boston.commands import flat_command
from .modules.general import take_exposures
from .. import util
from .. import calibration_util
from ..config import CONFIG_INI
import matplotlib.pyplot as plt


class UpdateSubarray(Experiment):
    name = "Update Subarray"
    log = logging.getLogger(__name__)

    def __init__(self,
                 dm1_command_object=flat_command(bias=False, flat_map=True),  # Default flat with bias.
                 dm2_command_object=flat_command(bias=False, flat_map=True),  # Default flat with bias.
                 exposure_time=quantity(250, units.microsecond),
                 camera_type="imaging_camera",
                 output_path=None,
                 exposure_set_name=None,
                 filename=None,
                 suffix=None,
                 **kwargs):
        """
        Takes a set of data with any camera, any DM command, any exposure time, etc.
        :param dm1_command_object: (DmCommand) DmCommand object to apply on a DM.
        :param exposure_time: (pint.quantity) Pint quantity for exposure time.
        :param num_exposures: (int) Number of exposures.
        :param step: (int) Step size to use for the motor positions (default is 10).
        :param output_path: (string) Path to save data.
        :param camera_type: (string) Camera type, maps to the [tested] section in the ini.
        :param position_list: (list) Postion(s) of the camera
        :param kwargs: Parameters for either the run_hicat_imaging function or the camera itself.
        """

        super(UpdateSubarray, self).__init__(output_path=output_path, suffix=suffix, **kwargs)

        self.dm1_command_object = dm1_command_object
        self.dm2_command_object = dm2_command_object
        self.exposure_time = exposure_time
        self.camera_type = camera_type
        self.exposure_set_name = exposure_set_name
        self.filename = filename
        self.kwargs = kwargs

    def experiment(self):
        path = take_exposures(self.dm1_command_object,
                              self.dm2_command_object,
                              self.exposure_time,
                              1,  # Number of exposures
                              self.camera_type,
                              False,  # Coronograph
                              False,  # Pipeline
                              self.output_path,
                              self.filename,
                              self.exposure_set_name,
                              self.suffix,
                              **self.kwargs)

        # Open the raw image and use the PSF to find the center.
        file_path = path[0]
        psf_image = util.read_fits(file_path, return_header=False)

        # Find the brightest peak (should be the core of the psf).
        mean, median, std = sigma_clipped_stats(psf_image, sigma=3)
        threshold = median + 10 * std
        box_size = int(round(.02 * psf_image.shape[0]))
        peak_table = find_peaks(psf_image, threshold, box_size=box_size, npeaks=1)

        # Extract coordinates from photutils table.
        coords = [(y, x) for y, x in zip(peak_table['x_peak'], peak_table['y_peak'])][0]

        # Get the current imaging camera subarray values.
        camera = CONFIG_INI.get("testbed", "imaging_camera")
        subarray_x = CONFIG_INI.getint(camera, "subarray_x")
        subarray_y = CONFIG_INI.getint(camera, "subarray_y")

        # Calculate offsets to apply.
        center_x = int(psf_image.shape[0] / 2)
        center_y = int(psf_image.shape[1] / 2)
        offset_x = center_x - coords[0]
        offset_y = center_y - coords[1]
        print("centroid: " + str(coords))
        print("subarray_x = " + str(subarray_x - offset_x))
        print("subarray_y = " + str(subarray_y - offset_y))
