import numpy as np
import logging
import os
import csv
from astropy.io import fits

from hicat.experiments.Experiment import Experiment
from catkit.hardware.boston.commands import poke_letter_f_command, poke_command, flat_command
from catkit.hardware.boston import DmCommand
from hicat.hardware import testbed
from catkit.hardware.FourDTechnology.Accufiz import Accufiz
from hicat.config import CONFIG_INI
import hicat.util
from hicat.hicat_types import units, quantity
from hicat import wavefront_correction


class Take4dImageDmCommand(Experiment):
    """
    Simple experiment to load any DMCommand and take a 4D Image.

    Args:
        mask (string): Name of mask file located on 4D pc.
        num_frames (int): Number of frames to take and average on the 4D
        path (string): Path to store images (default is to central store).
        filename (string): Filename override
        dm_num (int): Which DM to apply the pokes to.
        rotate (int): Amount to rotate images that are returned from 4d (increments of 90).
        fliplr (bool): Apply a flip left/right to the image returned from the 4d.
        command (DmCommand): DmCommand object to apply.
        reference_command (DmCommand): DmCommand to use as a reference to subtract from the image.
        suffix (string): String to append to the folder where the data is stored.
        **kwargs: Placeholder.
    """

    name = "Take 4d Image DM Command"
    log = logging.getLogger(__name__)

    def __init__(self,
                 mask="dm1_detector.mask",
                 num_frames=2,
                 output_path=None,
                 filename=None,
                 dm_num=1,
                 rotate=180,
                 fliplr=False,
                 command=flat_command(flat_map=True),
                 reference_command=None,
                 suffix="Take4dImageDmCommand",
                 **kwargs):

        super(Take4dImageDmCommand, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        if filename is None:
            filename = "4d_"

        self.mask = mask
        self.num_frames = num_frames
        self.output_path = output_path
        self.filename = filename
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.command = command
        self.reference_command = reference_command
        self.suffix = suffix
        self.kwargs = kwargs

    def experiment(self):

        # Read in the actuator map into a dictionary.
        map_file_name = "actuator_map_dm1.csv" if self.dm_num == 1 else "actuator_map_dm2.csv"
        mask_path = os.path.join(hicat.util.find_package_location(), "hardware", "FourDTechnology", map_file_name)
        actuator_index = {}
        with open(mask_path) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                actuator_index[int(row['actuator'])] = (int(row['x_coord']), int(row['y_coord']))

        # Start with a bias on the DM.
        with testbed.dm_controller() as dm:
            dm.apply_shape(self.command, self.dm_num)

            print("Taking 4D image...")
            with Accufiz("4d_accufiz", mask=self.mask) as four_d:
                file_name = "4dImage" if self.suffix == "" else "4dImage_" + self.suffix
                image_path = four_d.take_measurement(path=os.path.join(self.output_path, "raw"),
                                                     filename=file_name,
                                                     rotate=self.rotate,
                                                     num_frames=self.num_frames,
                                                     fliplr=self.fliplr)

                # Take a reference image and subtract.
                if self.reference_command is not None:
                    print("Taking reference image...")
                    dm.apply_shape(self.reference_command, self.dm_num)
                    reference_path = four_d.take_measurement(path=os.path.join(self.output_path, "reference"),
                                                             filename="reference_flat",
                                                             rotate=self.rotate,
                                                             num_frames=self.num_frames,
                                                             fliplr=self.fliplr)  # Open fits files and subtract.
                    reference = fits.getdata(reference_path)
                    image = fits.getdata(image_path)

                    # Subtract the reference from image.
                    hicat.util.write_fits(reference - image, os.path.join(self.output_path, file_name + "_subtracted"))

            # Save the DM_Command used.
            self.command.export_fits(os.path.join(self.output_path, file_name))
