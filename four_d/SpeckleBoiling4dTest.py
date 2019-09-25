import logging
import os
from glob import glob

from astropy.io import fits

from hicat.experiments.Experiment import Experiment
from hicat import util
from hicat.config import CONFIG_INI
from hicat.hardware import testbed
from hicat.hardware.FourDTechnology.Accufiz import Accufiz
from hicat.hardware.boston.DmCommand import DmCommand
from hicat.hardware.boston.commands import flat_command

class SpeckleBoiling4dTest(Experiment):
    """
    Loads each iteration of DM commands from a speckle nulling experiemnt, and takes a 4D image.  The data
    should be analyzed to explore why and when speckle boiling occurs.

    Args:
        speckle_nulling_path (string): Path to root directory of a speckle nulling experiment.
        mask (string): Name of mask file located on 4D pc.
        num_frames (int): Number of frames to take and average on the 4D
        path (string): Path to store images (default is to central store).
        filename (string): Filename override
        dm_num (int): Which DM to apply the pokes to.
        rotate (int): Amount to rotate images that are returned from 4d (increments of 90).
        fliplr (bool): Apply a flip left/right to the image returned from the 4d.
        **kwargs:
    """

    name = "4D Speckle Boiling Test"
    log = logging.getLogger(__name__)

    def __init__(self,
                 speckle_nulling_path="Z:/Testbeds/hicat_dev/data/2018-02-27T14-12-04_speckle_nulling/",
                 mask="dm1_detector.mask",
                 num_frames=4,
                 output_path=None,
                 filename=None,
                 dm_num=1,
                 rotate=180,
                 fliplr=False,
                 suffix="4dSpeckleBoilingTest",
                 **kwargs):

        super(SpeckleBoiling4dTest, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.mask = mask
        self.speckle_nulling_path = speckle_nulling_path
        self.num_frames = num_frames
        self.filename = filename
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.kwargs = kwargs

    def experiment(self):

        # Glob the directories of specklenulling and order them by iteration number.
        folder_paths = glob(os.path.join(self.speckle_nulling_path, "*iteration*"))
        itr_string = "iteration"
        sorted_folder_paths = sorted(folder_paths, key=lambda x: int(x[x.find(itr_string) + len(itr_string):]))

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

                for path in sorted_folder_paths:
                    # Get DM Command fits and convert to volts.
                    dm_command_path = os.path.join(path, "coron", "dm_command", "dm_command_2d.fits")
                    data = fits.getdata(dm_command_path)
                    data *= 200

                    # Create DmCommand object and apply the shape to the DM.
                    current_command_object = DmCommand(data, 1, flat_map=False, bias=False, as_volts=True)
                    dm.apply_shape(current_command_object, self.dm_num)

                    # Take 4d Image.
                    file_name = path[path.find(itr_string):]
                    four_d.take_measurement(path=os.path.join(self.output_path, file_name),
                                            filename=file_name,
                                            rotate=self.rotate,
                                            num_frames=self.num_frames,
                                            fliplr=self.fliplr)

                    # Save the DM_Command used.
                    current_command_object.export_fits(os.path.join(self.output_path, file_name))
