from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import numpy as np
import os
from astropy.io import fits

from hicat.hicat_types import MetaDataEntry
from .Experiment import Experiment
from ..hardware.boston.commands import poke_letter_f_command, poke_command, checkerboard_command, flat_command
from ..hardware import testbed
from ..hardware.FourDTechnology.Accufiz import Accufiz
from ..config import CONFIG_INI
from .. import util
from ..hicat_types import units, quantity


class TakeDm4dCheckerboardData(Experiment):
    name = "Take Dm 4d Checkerboard Data"

    def __init__(self,
                 amplitude_range=[700],
                 mask="dm2_detector.mask",
                 num_frames=2,
                 path=None,
                 dm_num=2,
                 rotate=0,
                 fliplr=False,
                 **kwargs):
        if path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "data_path")
            path = util.create_data_path(initial_path=central_store_path, suffix="4d_checkerboard")

        self.amplitude_range = amplitude_range
        self.mask = mask
        self.num_frames = num_frames
        self.path = path
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.kwargs = kwargs

    def experiment(self):

        mask = "dm2_detector.mask" if self.dm_num == 2 else "dm1_detector.mask"

        with testbed.dm_controller() as dm:

            # Reference flat image.
            with Accufiz("4d_accufiz", mask=mask) as four_d:
                flat_dm_command = flat_command(bias=False, flat_map=True)
                dm.apply_shape(flat_dm_command, dm_num=self.dm_num)
                reference_path = four_d.take_measurement(path=self.path,
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
                        with Accufiz("4d_accufiz", mask=mask) as four_d:
                            image_path = four_d.take_measurement(path=os.path.join(self.path, file_name),
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
                            util.write_fits(reference - image, os.path.join(self.path, file_name + "_subtracted"),
                                            metadata=metadata)


                            # Save the DM_Command used.
                            command.export_fits(os.path.join(self.path, file_name))
