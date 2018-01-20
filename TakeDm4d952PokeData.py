from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import os
from glob import glob
from photutils import find_peaks
from astropy.io import fits
import matplotlib.pyplot as plt

from .Experiment import Experiment
from ..hardware.boston.commands import poke_command
from ..hardware import testbed
from ..hardware.FourDTechnology.Accufiz import Accufiz
from ..config import CONFIG_INI
from .. import util
from .. hicat_types import quantity, units


class TakeDm4d952PokeData(Experiment):
    name = "Take Dm 4d 952 Poke Data"

    def __init__(self,
                 mask="dm2_detector.mask",
                 num_frames=3,
                 path=None,
                 dm_num=2,
                 rotate=0,
                 fliplr=False,
                 show_plot=False,
                 create_csv=True,
                 **kwargs):
        if path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "data_path")
            path = util.create_data_path(initial_path=central_store_path, suffix="4d_952_poke")

        self.mask = mask
        self.num_frames = num_frames
        self.path = path
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.show_plot = show_plot
        self.create_csv = create_csv
        self.kwargs = kwargs

    def experiment(self):

        mask = "dm2_detector.mask" if self.dm_num == 2 else "dm1_detector.mask"

        # with Accufiz("4d_accufiz", mask=mask) as four_d:
        #     # Reference image.
        #     reference_path = four_d.take_measurement(path=self.path,
        #                                              filename="reference",
        #                                              rotate=self.rotate,
        #                                              fliplr=self.fliplr)
        #
        # with testbed.dm_controller() as dm:
        #     # Generate the 16 permutations of checkerboards, and add the commands to a list.
        #     for i in range(0, 952):
        #         file_name = "poke_actuator_{}".format(i)
        #         command = poke_command(i, amplitude=quantity(800, units.nanometers), dm_num=self.dm_num)
        #
        #         dm.apply_shape(command, self.dm_num)
        #         with Accufiz("4d_accufiz", mask=mask) as four_d:
        #             image_path = four_d.take_measurement(path=os.path.join(self.path, file_name),
        #                                                  num_frames=self.num_frames,
        #                                                  filename=file_name,
        #                                                  rotate=self.rotate,
        #                                                  fliplr=self.fliplr)
        #
        #             # Open fits files and subtract.
        #             reference = fits.getdata(reference_path)
        #             image = fits.getdata(image_path)
        #
        #             # Subtract the reference from image.
        #             util.write_fits(reference - image, os.path.join(self.path, file_name + "_subtracted"))
        #
        #             # Save the DM_Command used.
        #             command.export_fits(os.path.join(self.path, file_name))

        if self.create_csv:
            self.create_actuator_index()

    def create_actuator_index(self):
        root_dir = util.find_package_location()
        csv_filename = "actuator_map_dm1.csv" if self.dm_num == 1 else " actuator_map_dm2.csv"

        self.path = "Z:/Testbeds/hicat_dev/data/2018-01-19T18-30-13_4d_952_poke"
        csv_file = os.path.join(self.path, csv_filename)

        actuator_indices = {}
        num_actuators = CONFIG_INI.getint("boston_kilo952", "number_of_actuators")
        for i in range(num_actuators):

            # Open the correct poke file.
            #poke_file = glob(os.path.join(self.path + "*_" + str(i) + "_subtracted.fits"))[0]

            #print("self.path: ",self.path)
            #print(os.path.join(self.path , "*_" + str(i) + "_subtracted.fits"))
            #print(glob(os.path.join(self.path , "*_" + str(i) + "_subtracted.fits")))
            poke_file = glob(os.path.join(self.path , "*_" + str(i) + "_subtracted.fits"))[0]
            #print(poke_file)

            # Get the data
            data = fits.getdata(poke_file)

            # Find the centroid of the poke.
            table = find_peaks(data, data.max() * .95, npeaks=1)
            x_peak = table["x_peak"][0]
            y_peak = table["y_peak"][0]
            coord = (x_peak, y_peak)

            actuator_indices[i] = coord
            print(i)

        if self.show_plot:
            plt.figure(figsize=(10, 8))
            ref_image = fits.getdata(os.path.join(self.path, "reference.fits"))
            plt.imshow(ref_image)
            plt.title("Number of actuators: {}".format(len(actuator_indices)))
            plt.show()

        csv_list = []
        for key, r in actuator_indices.items():
            plt.scatter(r[0], r[1], color='black', s=6)
            csv_list.append(str(key) + "," + str(r[0]) + "," + str(r[1]))
        plt.show()

        with open(csv_file, "wb") as csvfile:
            csvfile.write(str("actuator,x_coord,y_coord\n"))
            for row in csv_list:
                csvfile.write(row + "\n")
