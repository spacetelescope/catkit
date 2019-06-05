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

from hicat.experiments.modules import zernike as my_zernike_module
from hicat.experiments.Experiment import Experiment
from hicat.hardware.boston.commands import poke_letter_f_command, poke_command, flat_command
from hicat.hardware.boston.DmCommand import get_flat_map_volts, convert_volts_to_nm
from hicat.hardware import testbed
from hicat.hardware.FourDTechnology.Accufiz import Accufiz
from hicat.config import CONFIG_INI
from hicat import util
from hicat.hicat_types import units, quantity
from hicat import wavefront_correction


class Dm4dShapeLoop(Experiment):
    """
    Iterates to a DM command to match an arbitrary shape (numpy array).

    Args:
        shape: (numpy array): Numpy shape to iterate the DM to match.
        amplitude (list(int)): list of amplitudes to create commands for.
        mask (string): Name of mask file located on 4D pc.
        num_frames (int): Number of frames to take and average on the 4D
        path (string): Path to store images (default is to central store).
        filename (string): Filename override
        dm_num (int): Which DM to apply the pokes to.
        rotate (int): Amount to rotate images that are returned from 4d (increments of 90).
        fliplr (bool): Apply a flip left/right to the image returned from the 4d.
        iterations (int): Number of iterations to flatten the DM.
        damping_ratio (float): Damping ratio to apply to the flat command applied each iteration.
        create_command (bool): Create a fits DM command with the best zernike map.
        suffix (string): Additional string to append to the folder where the data is stored.
        **kwargs: Placeholder
    """

    name = "Dm 4d Shape Loop"
    log = logging.getLogger(__name__)

    def __init__(self,
                 shape,
                 amplitude=[100],
                 mask="dm1_detector.mask",
                 num_frames=2,
                 output_path=None,
                 filename=None,
                 dm_num=1,
                 rotate=180,
                 fliplr=False,
                 iterations=15,
                 damping_ratio=.6,
                 create_command=True,
                 suffix="4d_shape_loop" ,
                 **kwargs):

        super(self, Experiment).__init__(output_path=output_path, suffix=suffix, **kwargs)
        if filename is None:
            filename = "4d_"

        self.shape = shape
        self.amplitude = amplitude
        self.mask = mask
        self.num_frames = num_frames
        self.path = output_path
        self.filename = filename
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.iterations = iterations
        self.damping_ratio = damping_ratio
        self.create_command = create_command
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

        # Start with a flat on the DM.
        actuator_intensities = {}
        with testbed.dm_controller() as dm:

            command_object = flat_command(bias=False,
                                          flat_map=True,
                                          return_shortname=False,
                                          dm_num=self.dm_num)

            dm.apply_shape(command_object, self.dm_num)

            print("Taking initial image...")
            with Accufiz("4d_accufiz", mask=self.mask) as four_d:
                initial_file_name = "initial_flat"
                image_path = four_d.take_measurement(path=os.path.join(self.path, initial_file_name),
                                                     filename=initial_file_name,
                                                     rotate=self.rotate,
                                                     num_frames=self.num_frames,
                                                     fliplr=self.fliplr)

                # Save the DM_Command used.
                command_object.export_fits(os.path.join(self.path, initial_file_name))

                if isinstance(self.amplitude, int):
                    self.amplitude = [self.amplitude]

                for amp_nm in self.amplitude:
                    best_std_deviation = None
                    best_command = None
                    p2v_string = str(amp_nm) + "_nm_amplitude"

                    # Normalize and multiply peak to valley.
                    renormalized_shape = self.shape * amp_nm

                    # Create the 1d shape.
                    shape_1d = util.convert_dm_image_to_command(renormalized_shape)

                    for i in range(self.iterations):
                        image = fits.getdata(image_path)

                        print("Finding intensities...")
                        for key, value in actuator_index.items():
                            # Create a small circle mask around index, and take the median.
                            actuator_mask = wavefront_correction.circle_mask(image, value[0], value[1], 3)

                            # Find the median within the mask.
                            actuator_intensity = np.median(image[actuator_mask])

                            # Add to intensity dictionary.
                            actuator_intensities[key] = actuator_intensity

                        # Find the median of all the intensities and bias the shape.
                        if i == 0:
                            flat_value = np.median(np.array(list(actuator_intensities.values())))
                            print("FLAT Value " + str(flat_value))
                            shape_1d += flat_value

                        # Calculate and print the variance and standard deviation.
                        intensity_values = np.array(list(actuator_intensities.values()))
                        diff = shape_1d - intensity_values
                        print("Variance: ", np.var(diff))
                        std_deviation = np.std(diff)
                        print("Standard deviation: ", std_deviation)

                        if best_std_deviation is None or std_deviation < best_std_deviation:
                            best_std_deviation = std_deviation
                            best_command = i

                        # Generate the correction values.
                        print("Generating corrections...")
                        corrected_values = []
                        for key, value in actuator_intensities.items():

                            correction = quantity(value - shape_1d[key], units.nanometer).to_base_units().m

                            # Apply damping ratio.
                            correction *= self.damping_ratio
                            corrected_values.append(correction)


                        # Update the DmCommand.
                        command_object.data += util.convert_dm_command_to_image(corrected_values)

                        # Apply the new command.
                        dm.apply_shape(command_object, dm_num=self.dm_num)

                        print("Taking exposures with 4D...")
                        file_name = "iteration{}".format(i)
                        util.write_fits(util.convert_dm_command_to_image([i * 1e9 for i in corrected_values]),
                                        os.path.join(self.path, p2v_string, file_name, "correction"))

                        image_path = four_d.take_measurement(path=os.path.join(self.path, p2v_string, file_name),
                                                             filename=file_name,
                                                             rotate=self.rotate,
                                                             num_frames=self.num_frames,
                                                             fliplr=self.fliplr)

                        # Save the DM_Command used.
                        command_object.export_fits(os.path.join(self.path, p2v_string, file_name))

                    # Subtract the reference from image.
                    dm.apply_shape(flat_command(bias=False,
                                                flat_map=True,
                                                return_shortname=False,
                                                dm_num=self.dm_num),
                                   self.dm_num)

                    print("Taking reference image to make final subtracted fits file...")
                    reference_image_path = four_d.take_measurement(
                        path=os.path.join(self.path, p2v_string),
                        filename="final_reference",
                        rotate=self.rotate,
                        num_frames=self.num_frames,
                        fliplr=self.fliplr)
                    raw_image = fits.getdata(image_path)
                    reference = fits.getdata(reference_image_path)
                    util.write_fits(raw_image - reference,
                                    os.path.join(self.path, p2v_string, file_name + "_subtracted"))

                if self.create_command:
                    iteration_folder_name = "iteration" + str(best_command)
                    full_path = os.path.join(self.path, p2v_string, iteration_folder_name, "dm_command",
                                             "dm_command_2d.fits")
                    dm_command_data = fits.getdata(full_path)

                    # Convert the dm command units to volts.
                    max_volts = CONFIG_INI.getint("boston_kilo952", "max_volts")
                    dm_command_data *= max_volts

                    # Add the Zernike name to the file name.
                    filename = "shape_volts_dm1.fits" if self.dm_num == 1 else "shape_volts_dm2.fits"
                    util.write_fits(dm_command_data, os.path.join(self.path, p2v_string, filename))
