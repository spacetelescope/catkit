import logging
import os
from glob import glob

import matplotlib.pyplot as plt
from astropy.io import fits
from photutils import find_peaks
import shutil

from hicat.experiments.Experiment import Experiment
import hicat.util
from hicat.config import CONFIG_INI
from hicat.hardware import testbed
from catkit.hardware.FourDTechnology.Accufiz import Accufiz
from catkit.hardware.boston.commands import poke_command, flat_command
from hicat.hicat_types import quantity, units


class TakeDm4d952PokeData(Experiment):
    """
    Experiment used for creating an actuator mapping used for the other command creating experiments.  Pokes
    each actuator, takes an image, identifies where the poke occured and generates an index file.

    Args:
        mask (string): Name of mask file located on 4D pc.
        num_frames (int): Number of frames to take and average on the 4D
        path (string): Path to store images (default is to central store).
        filename (string): Filename override
        dm_num (int): Which DM to apply the pokes to.
        rotate (int): Amount to rotate images that are returned from 4d (increments of 90).
        fliplr (bool): Apply a flip left/right to the image returned from the 4d.
        show_plot (bool): Plot each of the identified pokes for each iteration.
        overwrite_csv (bool): Move the newly created index csv file into hicat
        start_actuator (int): If you wish to resume a crashed experiment, you can skip some actuators with this.
        reference (bool): Applies a flat and subtracts it from the poked image.
        **kwargs: Placeholder.
    """

    name = "Take Dm 4d 952 Poke Data"
    log = logging.getLogger(__name__)

    def __init__(self,
                 mask="dm2_detector.mask",
                 num_frames=3,
                 output_path=None,
                 dm_num=1,
                 rotate=0,
                 fliplr=False,
                 show_plot=False,
                 overwrite_csv=False,
                 start_actuator=0,
                 reference=True,
                 suffix="4d_952_poke",
                 **kwargs):

        super(TakeDm4d952PokeData, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.mask = mask
        self.num_frames = num_frames
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.show_plot = show_plot
        self.overwrite_csv = overwrite_csv
        self.start_actuator = start_actuator
        self.reference = reference
        self.kwargs = kwargs

    def experiment(self):

        mask = "dm2_detector.mask" if self.dm_num == 2 else "dm1_detector.mask"

        with testbed.dm_controller() as dm:

            command = flat_command(bias=False,
                                   flat_map=True,
                                   return_shortname=False,
                                   dm_num=self.dm_num)

            dm.apply_shape(command, self.dm_num)
            with Accufiz("4d_accufiz", mask=mask) as four_d:
                # Reference image.
                if self.reference:
                    reference_path = four_d.take_measurement(path=self.output_path,
                                                             filename="reference",
                                                             rotate=self.rotate,
                                                             fliplr=self.fliplr)
                else:
                    reference_path = glob(os.path.join(self.output_path, "reference.fits"))[0]
                # Poke every actuator, one at a time.
                num_actuators = CONFIG_INI.getint("boston_kilo952", "number_of_actuators")
                for i in range(self.start_actuator, num_actuators):
                    file_name = "poke_actuator_{}".format(i)
                    command = poke_command(i, amplitude=quantity(200, units.nanometers), dm_num=self.dm_num)

                    dm.apply_shape(command, self.dm_num)
                    image_path = four_d.take_measurement(path=os.path.join(self.output_path, file_name),
                                                         num_frames=self.num_frames,
                                                         filename=file_name,
                                                         rotate=self.rotate,
                                                         fliplr=self.fliplr)

                    # Open fits files and subtract.
                    reference = fits.getdata(reference_path)
                    image = fits.getdata(image_path)

                    # Subtract the reference from image.
                    hicat.util.write_fits(reference - image, os.path.join(self.output_path, file_name + "_subtracted"))

                    # Save the DM_Command used.
                    command.export_fits(os.path.join(self.output_path, file_name))

        self.create_actuator_index()

    def create_actuator_index(self):
        csv_filename = "actuator_map_dm1.csv" if self.dm_num == 1 else "actuator_map_dm2.csv"
        csv_file_path = os.path.join(self.output_path, csv_filename)

        actuator_indices = {}
        num_actuators = CONFIG_INI.getint("boston_kilo952", "number_of_actuators")
        for i in range(num_actuators):
            # Open the correct poke file.
            poke_file = glob(os.path.join(self.output_path, "*_" + str(i) + "_subtracted.fits"))[0]

            # Get the data
            data = fits.getdata(poke_file)

            # Find the centroid of the poke.
            table = find_peaks(data, data.max() * .95, npeaks=1)
            x_peak = table["x_peak"][0]
            y_peak = table["y_peak"][0]
            coord = (x_peak, y_peak)

            actuator_indices[i] = coord
            self.log.debug(i)

        csv_list = []
        for key, r in actuator_indices.items():
            plt.scatter(r[0], r[1], color='black', s=6)
            csv_list.append(str(key) + "," + str(r[0]) + "," + str(r[1]))

        if self.show_plot:
            plt.figure(figsize=(10, 8))
            ref_image = fits.getdata(os.path.join(self.output_path, "reference.fits"))
            plt.imshow(ref_image)
            plt.title("Number of actuators: {}".format(len(actuator_indices)))
            plt.show()

        with open(csv_file_path, "wb") as csvfile:
            csvfile.write(str("actuator,x_coord,y_coord\n"))
            for row in csv_list:
                csvfile.write(row + "\n")

        if self.overwrite_csv:
            root_dir = hicat.util.find_package_location()
            package_csv_file = os.path.join(root_dir, csv_filename)
            shutil.copy(csv_file_path, package_csv_file)

