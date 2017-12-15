from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import numpy as np
import os
import csv
from astropy.io import fits

from .Experiment import Experiment
from ..hardware.boston.commands import poke_letter_f_command, poke_command, flat_command
from ..hardware import testbed
from ..hardware.FourDTechnology.Accufiz import Accufiz
from ..config import CONFIG_INI
from .. import util
from ..hicat_types import units, quantity
from .. import dm_calibration_util


class Dm4dFlatMapLoop(Experiment):
    name = "Dm 4d Actuator Analysis"

    def __init__(self,
                 mask="dm2_detector.mask",
                 num_frames=2,
                 path=None,
                 filename=None,
                 dm_num=2,
                 rotate=180,
                 fliplr=False,
                 **kwargs):
        if path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "data_path")
            path = util.create_data_path(initial_path=central_store_path, suffix="4d")

        if filename is None:
            filename = "4d_"

        self.mask = mask
        self.num_frames = num_frames
        self.path = path
        self.filename = filename
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.kwargs = kwargs

    def experiment(self):

        # Read in the actuator map into a dictionary.
        map_file_name = "actuator_map_dm1.csv" if self.dm_num == 1 else "actuator_map_dm2.csv"
        repo_path = util.find_repo_location()
        mask_path = os.path.join(repo_path, "hardware", "FourDTechnology", map_file_name)
        actuator_index = {}
        with open(mask_path) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                actuator_index[int(row['actuator'])] = (int(row['x_coord']), int(row['y_coord']))

        # Take Reference image.
        with Accufiz("4d_accufiz", mask=self.mask) as four_d:
            reference_path = four_d.take_measurement(path=self.path,
                                                     filename="reference",
                                                     rotate=self.rotate,
                                                     fliplr=self.fliplr)

        # Start with a bias on the DM.
        actuator_intensities = {}
        with testbed.dm_controller() as dm:
            flat_command_object = flat_command(bias=True,
                                               flat_map=False,
                                               return_shortname=False,
                                               dm_num=2)
            dm.apply_shape(flat_command_object, self.dm_num)

            with Accufiz("4d_accufiz", mask=self.mask) as four_d:
                initial_file_name = "initial_bias"
                image_path = four_d.take_measurement(path=os.path.join(self.path, initial_file_name),
                                                     filename=initial_file_name,
                                                     rotate=self.rotate,
                                                     fliplr=self.fliplr)

                # Open fits files and subtract.
                reference = fits.getdata(reference_path)
                image = fits.getdata(image_path)

                # Subtract the reference from image.
                initial_subtracted_image_path = os.path.join(self.path, initial_file_name + "_subtracted")
                util.write_fits(reference - image, initial_subtracted_image_path)

                # Save the DM_Command used.
                flat_command_object.export_fits(os.path.join(self.path, initial_file_name))

                # Using the actuator_map, find the intensities at each actuator pixel value.
                initial_subtracted_image = reference = fits.getdata(initial_subtracted_image_path)
                for key, value in actuator_index:

                    # Create a small circle mask around index, and take the median.
                    actuator_mask = dm_calibration_util.circle_mask(initial_subtracted_image, value[0], value[1], 3)

                    # Find the median within the mask.
                    actuator_intensity = np.median(actuator_mask)

                    # Add to intensity dictionary.
                    actuator_intensities[key] = actuator_intensity

                print(actuator_intensities)