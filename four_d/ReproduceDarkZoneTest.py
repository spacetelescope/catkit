import logging
import os
from glob import glob

from astropy.io import fits
import numpy as np
import time

from hicat.experiments.Experiment import Experiment
from hicat import util
from hicat.config import CONFIG_INI
from hicat.hardware import testbed
from catkit.hardware.FourDTechnology.Accufiz import Accufiz
from catkit.hardware.boston.DmCommand import DmCommand
from catkit.hardware.boston.commands import flat_command


class ReproduceDarkZoneTest(Experiment):
    """
    Loads a dark zone DM command created by running speckle nulling (or other future experiments), and iterates
    toward that command in front of a 4D.

    Args:
        darkzone_command_path (string): Path to a dm command fits that commands a deep dark zone onto the DM.
        iterations (int): Number of iterations to flatten the DM.
        mask (string): Name of mask file located on 4D pc.
        num_frames (int): Number of frames to take and average on the 4D
        path (string): Path to store images (default is to central store).
        filename (string): Filename override
        dm_num (int): Which DM to apply the pokes to.
        rotate (int): Amount to rotate images that are returned from 4d (increments of 90).
        fliplr (bool): Apply a flip left/right to the image returned from the 4d.
        **kwargs: Placeholder
    """

    name = "Reproduce Dark Zone Test"
    log = logging.getLogger(__name__)

    def __init__(self,
                 darkzone_command_path="Z:/Testbeds/hicat_dev/data/2018-02-27T14-12-04_speckle_nulling/iteration427/coron/dm_command/dm_command_2d.fits",
                 iterations=10,
                 mask="dm1_detector.mask",
                 num_frames=10,
                 output_path=None,
                 filename=None,
                 dm_num=1,
                 rotate=180,
                 fliplr=False,
                 suffix="ReproduceDarkZoneTest",
                 **kwargs):

        super(ReproduceDarkZoneTest, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.darkzone_command_path = darkzone_command_path
        self.iterations = iterations
        self.mask = mask
        self.num_frames = num_frames
        self.output_path = output_path
        self.filename = filename
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.kwargs = kwargs

    def experiment(self):

        # Open darkzone command fits file.
        data = fits.getdata(self.darkzone_command_path)
        data *= 200

        print("Taking 4D images...")
        with Accufiz("4d_accufiz", mask=self.mask) as four_d:

            # Start with a bias on the DM.
            with testbed.dm_controller() as dm:

                    # Take a reference flat.
                    dm.apply_shape(flat_command(flat_map=True), self.dm_num)
                    four_d.take_measurement(path=self.output_path,
                                            filename="reference_flat",
                                            rotate=self.rotate,
                                            num_frames=self.num_frames,
                                            fliplr=self.fliplr)

                    # Get DM Command fits and convert to volts.
                    data = fits.getdata(self.darkzone_command_path)
                    data *= 200

                    # Create DmCommand object and apply the shape to the DM.
                    current_command_object = DmCommand(data, 1, flat_map=False, bias=False, as_volts=True)
                    zeros_command = DmCommand(np.zeros(data.shape), 1, flat_map=False, bias=False, as_volts=True)

                    # Save the DM_Command used.
                    current_command_object.export_fits(self.output_path)
                    for i in range(self.iterations):
                        print("Dark zone iteration " + str(i))
                        dm.apply_shape(current_command_object, self.dm_num)

                        # Take 4d Image.
                        four_d.take_measurement(path=os.path.join(self.output_path, "iteration" + str(i)),
                                                filename="darkzone",
                                                rotate=self.rotate,
                                                num_frames=self.num_frames,
                                                fliplr=self.fliplr)

                        # Zero out the Dm and pause for a few seconds.
                        dm.apply_shape(zeros_command, self.dm_num)
                        print("DM set to 0V")
                        time.sleep(5)
