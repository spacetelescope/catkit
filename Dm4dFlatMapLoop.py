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
    name = "Dm 4d Flat Map Loop"

    def __init__(self,
                 mask="dm2_detector.mask",
                 num_frames=2,
                 path=None,
                 filename=None,
                 dm_num=2,
                 rotate=180,
                 fliplr=False,
                 iterations=2,
                 damping_ratio=.5,
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
        self.iterations = iterations
        self.damping_ratio = damping_ratio
        self.kwargs = kwargs

    def experiment(self):

        # Read in the actuator map into a dictionary.
        map_file_name = "actuator_map_dm1.csv" if self.dm_num == 1 else "actuator_map_dm2.csv"
        repo_path = util.find_repo_location()
        mask_path = os.path.join(repo_path, "hicat", "hardware", "FourDTechnology", map_file_name)
        actuator_index = {}
        with open(mask_path) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                actuator_index[int(row['actuator'])] = (int(row['x_coord']), int(row['y_coord']))

        # Start with a bias on the DM.
        actuator_intensities = {}
        with testbed.dm_controller() as dm:

            command_object = flat_command(bias=True,
                                               flat_map=False,
                                               return_shortname=False,
                                               dm_num=2)
            dm.apply_shape(command_object, self.dm_num)

            print("Taking initial image...")
            with Accufiz("4d_accufiz", mask=self.mask) as four_d:
                initial_file_name = "initial_bias"
                image_path = four_d.take_measurement(path=os.path.join(self.path, initial_file_name),
                                                     filename=initial_file_name,
                                                     rotate=self.rotate,
                                                     num_frames=self.num_frames,
                                                     fliplr=self.fliplr)

                # Save the DM_Command used.
                command_object.export_fits(os.path.join(self.path, initial_file_name))

            flat_value = 0
            for i in range(self.iterations):
                # Using the actuator_map, find the intensities at each actuator pixel value.
                image = fits.getdata(image_path)

                print("Finding intensities...")
                for key, value in actuator_index.items():

                    # Create a small circle mask around index, and take the median.
                    actuator_mask = dm_calibration_util.circle_mask(image, value[0], value[1], 3)

                    # Find the median within the mask.
                    actuator_intensity = np.median(image[actuator_mask])

                    # Add to intensity dictionary.
                    actuator_intensities[key] = actuator_intensity

                # Find the median of all the intensities and use that as the "flat" value.
                if i == 0:
                    flat_value = np.median(np.array(list(actuator_intensities.values())))

                # Calculate and print the variance and standard deviation.
                intensity_values = np.array(list(actuator_intensities.values()))
                print("Variance: ", np.var(intensity_values))
                print("Standard deviation: ", np.std(intensity_values))

                # Generate the correction values.
                print("Generating corrections...")
                corrected_values = []
                for key, value in actuator_intensities.items():
                    correction = quantity(value - flat_value, units.nanometer).to_base_units().m

                    # Apply damping ratio.
                    correction *= self.damping_ratio
                    corrected_values.append(correction)

                # Update the DmCommand.
                command_object.data += util.convert_dm_command_to_image(corrected_values)

                # Apply the new command.
                dm.apply_shape(command_object, dm_num=self.dm_num)

                print("Taking exposures with 4D...")
                file_name = "iteration{}".format(i)
                image_path = four_d.take_measurement(path=os.path.join(self.path, file_name),
                                                     filename=file_name,
                                                     rotate=self.rotate,
                                                     num_frames=self.num_frames,
                                                     fliplr=self.fliplr)

                # Save the DM_Command used.
                command_object.export_fits(os.path.join(self.path, file_name))