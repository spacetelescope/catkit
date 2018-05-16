from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import numpy as np
import logging
import os
import csv
from astropy.io import fits

from .Experiment import Experiment
from ..hardware.boston.DmCommand import DmCommand
from .modules.phase_retrieval import take_phase_retrieval_data
from ..config import CONFIG_INI
from .. import util
from ..hicat_types import units, quantity
from .. import dm_calibration_util
from ..hardware.boston.commands import flat_command


class SinglePhaseRetrievalCommand(Experiment):
    name = "Single Phase Retrieval Command"
    log = logging.getLogger(__name__)

    def __init__(self,
                 input_image_path=None,
                 dm_num=1,
                 rotate=90,
                 fliplr=True,
                 damping_ratio=.6,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=5,
                 step=10,
                 path=None,
                 camera_type="phase_retrieval_camera",
                 position_list=None,
                 suffix=None,
                 **kwargs):

        self.input_image_path = input_image_path
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.damping_ratio = damping_ratio
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.step = step
        self.path = path
        self.camera_type = camera_type
        self.position_list = position_list
        self.suffix = suffix
        self.kwargs = kwargs

    def experiment(self):

        if self.path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "data_path")
            self.path = util.create_data_path(initial_path=central_store_path, suffix="brute_force")

        # Read in the actuator map into a dictionary.
        map_file_name = "actuator_map_dm1.csv" if self.dm_num == 1 else "actuator_map_dm2.csv"
        repo_path = util.find_repo_location()
        map_path = os.path.join(repo_path, "hicat", "phase_retrieval", map_file_name)
        actuator_index = {}
        with open(map_path) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                actuator_index[int(row['actuator'])] = (int(row['x_coord']), int(row['y_coord']))

        actuator_intensities = {}

        # Load phase retriveal input image, and find intensities.
        image = fits.getdata(self.input_image_path)

        # Apply rotates and flips.
        image = util.rotate_and_flip_image(image, self.rotate, self.fliplr)

        # Apply a -1 to the pr data.
        # image *= -1

        print("Finding intensities...")
        for key, value in actuator_index.items():
            # Create a small circle mask around index, and take the median.
            actuator_mask = dm_calibration_util.circle_mask(image, value[0], value[1], 3)

            # Find the median within the mask. Throw away values of zero, because they probably outside of the image.
            actuator_intensity = np.median(image[actuator_mask])

            # Add to intensity dictionary.
            actuator_intensities[key] = actuator_intensity

        # Generate the correction values.
        print("Generating corrections...")
        corrected_values = []
        for key, value in actuator_intensities.items():
            correction = quantity(value, units.nanometer).to_base_units().m

            # Apply the factor of 2 for the DM reflection.
            opd_scaling_dm = 1
            correction *= opd_scaling_dm

            # Apply damping ratio.
            correction *= self.damping_ratio
            corrected_values.append(correction)

        # Update the DmCommand.
        pr_command = DmCommand(util.convert_dm_command_to_image(corrected_values), 1, flat_map=True)

        print("Starting phase retrieval data set...")
        take_phase_retrieval_data(self.exposure_time,
                                  self.num_exposures,
                                  self.step,
                                  self.path,
                                  self.camera_type,
                                  position_list=self.position_list,
                                  dm1_command=pr_command,
                                  dm2_command=flat_command(False, True, dm_num=2),
                                  suffix=self.suffix,
                                  **self.kwargs)
