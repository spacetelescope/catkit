from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import numpy as np
import logging
import os
import csv
from astropy.io import fits

from hicat.experiments.Experiment import Experiment
from hicat.hardware.boston.commands import poke_letter_f_command, poke_command, flat_command
from hicat.hardware.boston import DmCommand
from hicat.hardware import testbed
from hicat.hardware.FourDTechnology.Accufiz import Accufiz
from hicat.config import CONFIG_INI
from hicat import util
from hicat.hicat_types import units, quantity
from hicat import wavefront_correction


class Dm4dFlatMapLoop(Experiment):
    name = "Dm 4d Flat Map Loop"
    log = logging.getLogger(__name__)

    def __init__(self,
                 mask="dm2_detector.mask",
                 num_frames=2,
                 path=None,
                 filename=None,
                 dm_num=2,
                 rotate=180,
                 fliplr=False,
                 iterations=20,
                 damping_ratio=.6,
                 create_flat_map=True,
                 initial_command_path=None,
                 **kwargs):

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
        self.create_flat_map = create_flat_map
        self.initial_command_path = initial_command_path
        self.kwargs = kwargs

    def experiment(self):

        if self.path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "data_path")
            self.path = util.create_data_path(initial_path=central_store_path, suffix="4d_flat_map_loop")

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
            if self.initial_command_path is None:
                command_object = flat_command(bias=True,
                                                   flat_map=False,
                                                   return_shortname=False,
                                                   dm_num=self.dm_num)
            else:
                command_object = DmCommand.load_dm_command(self.initial_command_path,
                                                               bias=True,
                                                               flat_map=False)
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
                best_std_deviation = None
                best_flat_map = None
                for i in range(self.iterations):
                    # Using the actuator_map, find the intensities at each actuator pixel value.
                    image = fits.getdata(image_path)

                    print("Finding intensities...")
                    for key, value in actuator_index.items():

                        # Create a small circle mask around index, and take the median.
                        actuator_mask = wavefront_correction.circle_mask(image, value[0], value[1], 3)

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
                    std_deviation = np.std(intensity_values)
                    print("Standard deviation: ", std_deviation)

                    if best_std_deviation is None or std_deviation < best_std_deviation:
                        best_std_deviation = std_deviation
                        best_flat_map = i

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

                if self.create_flat_map:
                    iteration_folder_name = "iteration" + str(best_flat_map)
                    full_path = os.path.join(self.path, iteration_folder_name, "dm_command", "dm_command_2d.fits")
                    dm_command_data = fits.getdata(full_path)

                    # Convert the dm command units to volts.
                    max_volts = CONFIG_INI.getint("boston_kilo952", "max_volts")
                    dm_command_data *= max_volts

                    filename = "flat_map_volts_dm1.fits" if self.dm_num == 1 else "flat_map_volts_dm2.fits"
                    root_dir = util.find_package_location()
                    full_output_path = os.path.join(root_dir, "hardware", "boston", filename)

                    util.write_fits(dm_command_data, full_output_path)
