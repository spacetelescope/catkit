from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import numpy as np
import os
import csv
import logging
from poppy import zernike
from astropy.io import fits

from .modules import zernike as my_zernike_module
from .Experiment import Experiment
from ..hardware.boston.commands import poke_letter_f_command, poke_command, flat_command
from ..hardware import testbed
from ..hardware.FourDTechnology.Accufiz import Accufiz
from ..config import CONFIG_INI
from .. import util
from ..hicat_types import units, quantity
from .. import dm_calibration_util


class Dm4dZernikeLoop(Experiment):
    name = "Dm 4d Zernike Loop"
    log = logging.getLogger(__name__)

    def __init__(self,
                 zernike_index=5,
                 peak2valley=[100],
                 mask="dm1_detector.mask",
                 num_frames=2,
                 path=None,
                 filename=None,
                 dm_num=1,
                 rotate=180,
                 fliplr=False,
                 iterations=30,
                 damping_ratio=.6,
                 create_zernike_map=True,
                 **kwargs):

        if filename is None:
            filename = "4d_"

        self.zernike_index = zernike_index
        self.peak2valley = peak2valley
        self.mask = mask
        self.num_frames = num_frames
        self.path = path
        self.filename = filename
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.iterations = iterations
        self.damping_ratio = damping_ratio
        self.create_zernike_map = create_zernike_map
        self.kwargs = kwargs

    def experiment(self):

        if self.path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "data_path")
            zernike_name = zernike.zern_name(self.zernike_index).replace(" ", "_").lower()
            self.path = util.create_data_path(initial_path=central_store_path, suffix="4d_zernike_loop_" + zernike_name)

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

            if isinstance(self.peak2valley, int):
                self.peak2valley = [self.peak2valley]

            for p2v in self.peak2valley:
                best_std_deviation = None
                best_zernike_command = None
                p2v_string = str(p2v) + "_nm_p2v"

                # Create the zernike shape.
                zernike_1d = util.convert_dm_image_to_command(my_zernike_module.create_zernike(self.zernike_index,p2v))

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

                    # Find the median of all the intensities and bias the zernike.
                    if i == 0:
                        flat_value = np.median(np.array(list(actuator_intensities.values())))
                        zernike_1d += flat_value

                    # Calculate and print the variance and standard deviation.
                    intensity_values = np.array(list(actuator_intensities.values()))
                    diff = intensity_values - zernike_1d
                    print("Variance: ", np.var(diff))
                    std_deviation = np.std(diff)
                    print("Standard deviation: ", std_deviation)

                    if best_std_deviation is None or std_deviation < best_std_deviation:
                        best_std_deviation = std_deviation
                        best_zernike_command = i

                    # Generate the correction values.
                    print("Generating corrections...")
                    corrected_values = []
                    for key, value in actuator_intensities.items():
                        correction = quantity(value - zernike_1d[key], units.nanometer).to_base_units().m

                        # Apply damping ratio.
                        correction *= self.damping_ratio
                        corrected_values.append(correction)

                    # Update the DmCommand.
                    command_object.data += util.convert_dm_command_to_image(corrected_values)

                    # Apply the new command.
                    dm.apply_shape(command_object, dm_num=self.dm_num)

                    print("Taking exposures with 4D...")
                    file_name = "iteration{}".format(i)

                    image_path = four_d.take_measurement(path=os.path.join(self.path, p2v_string, file_name),
                                                         filename=file_name,
                                                         rotate=self.rotate,
                                                         num_frames=self.num_frames,
                                                         fliplr=self.fliplr)

                    # Save the DM_Command used.
                    command_object.export_fits(os.path.join(self.path, p2v_string, file_name))

                if self.create_zernike_map:
                    iteration_folder_name = "iteration" + str(best_zernike_command)
                    full_path = os.path.join(self.path, p2v_string, iteration_folder_name, "dm_command", "dm_command_2d.fits")
                    dm_command_data = fits.getdata(full_path)

                    # Convert the dm command units to volts.
                    max_volts = CONFIG_INI.getint("boston_kilo952", "max_volts")
                    dm_command_data *= max_volts

                    # Add the Zernike name to the file name.
                    zernike_name = zernike.zern_name(self.zernike_index) + "_zernike"
                    filename = zernike_name + "_volts_dm1.fits" if self.dm_num == 1 else zernike_name + "_volts_dm2.fits"
                    util.write_fits(dm_command_data, os.path.join(self.path, p2v_string, filename))
