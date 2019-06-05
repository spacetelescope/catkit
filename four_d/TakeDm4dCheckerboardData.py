from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import os
from glob import glob
from astropy.io import fits

from hicat import wavefront_correction
from hicat.hicat_types import MetaDataEntry
from hicat.experiments.Experiment import Experiment
from hicat.hardware.boston.commands import poke_letter_f_command, poke_command, checkerboard_command, flat_command
from hicat.hardware import testbed
from hicat.hardware.FourDTechnology.Accufiz import Accufiz
from hicat.config import CONFIG_INI
from hicat import util
from hicat.hicat_types import units, quantity


class TakeDm4dCheckerboardData(Experiment):
    """
    Applies a set of 16 checkboard patterns to the DM that in effect pokes every actuator in a more
    efficient way than the 952 poke experiment.

    Args:
        amplitude_range (list(int)): list of amplitudes to create commands for.
        mask (string): Name of mask file located on 4D pc.
        num_frames (int): Number of frames to take and average on the 4D
        path (string): Path to store images (default is to central store).
        filename (string): Filename override
        dm_num (int): Which DM to apply the pokes to.
        rotate (int): Amount to rotate images that are returned from 4d (increments of 90).
        fliplr (bool): Apply a flip left/right to the image returned from the 4d.
        show_plot (bool): Plot each of the identified pokes for each iteration.
        overwrite_csv (bool): Move the newly created index csv file into hicat
        **kwargs: Placeholder.
    """

    name = "Take Dm 4d Checkerboard Data"

    def __init__(self,
                 amplitude_range=range(-2200, 850, 200),
                 mask="dm1_detector.mask",
                 num_frames=2,
                 output_path=None,
                 dm_num=1,
                 rotate=180,
                 fliplr=False,
                 show_plot=False,
                 overwrite_csv=False,
                 output_path=None,
                 suffix="4d_checkerboard",
                 **kwargs):

        super(TakeDm4dCheckerboardData, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.amplitude_range = amplitude_range
        self.mask = mask
        self.num_frames = num_frames
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.show_plot = show_plot
        self.overwrite_csv = overwrite_csv
        self.kwargs = kwargs

    def experiment(self):

        mask = "dm2_detector.mask" if self.dm_num == 2 else "dm1_detector.mask"

        with testbed.dm_controller() as dm:

            # Reference flat image.
            with Accufiz("4d_accufiz", mask=mask) as four_d:
                flat_dm_command = flat_command(bias=False, flat_map=True)
                dm.apply_shape(flat_dm_command, dm_num=self.dm_num)
                reference_path = four_d.take_measurement(path=self.output_path,
                                                         filename="reference",
                                                         rotate=self.rotate,
                                                         fliplr=self.fliplr)

                # Generate the 16 permutations of checkerboards, and add the commands to a list.
                for i in range(0, 4):
                    for j in range(0, 4):

                        for k in self.amplitude_range:
                            file_name = "checkerboard_{}_{}_{}nm".format(i, j, k)
                            command = checkerboard_command(dm_num=2, offset_x=i, offset_y=j,
                                                           amplitude=quantity(k, units.nanometers),
                                                           bias=False, flat_map=True)
                            dm.apply_shape(command, self.dm_num)
                            image_path = four_d.take_measurement(path=os.path.join(self.output_path, file_name),
                                                                 filename=file_name,
                                                                 rotate=self.rotate,
                                                                 fliplr=self.fliplr)

                            # Open fits files and subtract.
                            reference = fits.getdata(reference_path)
                            image = fits.getdata(image_path)

                            # Create metadata.
                            metadata = [MetaDataEntry("offset_x", "offset_x", i, "Checkerboard offset x-axis")]
                            metadata.append(MetaDataEntry("offset_y", "offset_y", j, "Checkerboard offset y-axis"))
                            metadata.append(MetaDataEntry("amplitude", "amp", k, "Amplitude in nanometers"))

                            # Subtract the reference from image.
                            util.write_fits(reference - image, os.path.join(self.output_path, file_name + "_subtracted"),
                                            metadata=metadata)

                            # Save the DM_Command used.
                            command.export_fits(os.path.join(self.output_path, file_name))

        # Old experimental code for creating an actuator index from checkerboards.
        # files_path = glob(os.path.join(self.path, file_name.split("_")[0] + "*_subtracted.fits"))
        # wavefront_correction.create_actuator_index(self.dm_num, path=self.path,
        #                                           files=files_path,
        #                                           reffiles=reference_path,
        #                                           show_plot=self.show_plot,
        #                                           overwrite_csv=self.overwrite_csv)
