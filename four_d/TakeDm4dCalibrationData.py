import numpy as np
import os
from astropy.io import fits

from hicat.experiments.Experiment import Experiment
from hicat.hardware.boston.commands import poke_letter_f_command, poke_command
from hicat.hardware import testbed
from hicat.hardware.FourDTechnology.Accufiz import Accufiz
from hicat.config import CONFIG_INI
from hicat import util


class TakeDm4dCalibrationData(Experiment):
    """
    Applies a DM Command and takes a 4D image that also gets a reference subtracted.

    Args:
        dm_command_object (DmCommand): DmCommand object to apply.
        mask (string): Name of mask file located on 4D pc.
        num_frames (int): Number of frames to take and average on the 4D
        path (string): Path to store images (default is to central store).
        filename (string): Filename override
        dm_num (int): Which DM to apply the pokes to.
        rotate (int): Amount to rotate images that are returned from 4d (increments of 90).
        fliplr (bool): Apply a flip left/right to the image returned from the 4d.
        **kwargs: Placeholder.
    """

    name = "Take Dm 4d Calibration Data"

    def __init__(self,
                 dm_command_object=None,
                 mask="dm2_detector.mask",
                 num_frames=2,
                 filename=None,
                 dm_num=2,
                 rotate=0,
                 fliplr=False,
                 output_path=None,
                 suffix='4d',
                 **kwargs):

        super(TakeDm4dCalibrationData, self).__init__(output_path=output_path, suffix=suffix, **kwargs)

        if filename is None:
            filename = "4d_"

        self.dm_command_object = dm_command_object
        self.mask = mask
        self.num_frames = num_frames
        self.output_path = output_path
        self.filename = filename
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.kwargs = kwargs

    def experiment(self):

        mask = "dm2_detector.mask" if self.dm_num == 2 else "dm1_detector.mask"

        with Accufiz("4d_accufiz", mask=mask) as four_d:
            # Reference image.
            reference_path = four_d.take_measurement(path=self.output_path,
                                                     num_frames=self.num_frames,
                                                     filename=self.filename + "_reference",
                                                     rotate=self.rotate,
                                                     fliplr=self.fliplr)

            with testbed.dm_controller() as dm:
                dm.apply_shape(self.dm_command_object, self.dm_num)
                image_path = four_d.take_measurement(path=self.output_path,
                                                     num_frames=self.num_frames,
                                                     filename=self.filename + "_command_image",
                                                     rotate=self.rotate,
                                                     fliplr=self.fliplr)

                # Open fits files and subtract.
                reference = fits.getdata(reference_path)
                image = fits.getdata(image_path)

                # Subtract the reference from image.
                util.write_fits(reference - image, os.path.join(self.output_path, self.filename + "_subtracted"))

                # Save the DM_Command used.
                self.dm_command_object.export_fits(self.output_path)
