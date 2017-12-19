from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import numpy as np
import os
from astropy.io import fits

from .Experiment import Experiment
from ..hardware.boston.commands import poke_letter_f_command, poke_command, checkerboard_command
from ..hardware import testbed
from ..hardware.FourDTechnology.Accufiz import Accufiz
from ..config import CONFIG_INI
from .. import util
from .. hicat_types import quantity, units


class TakeDm4d952PokeData(Experiment):
    name = "Take Dm 4d 952 Poke Data"

    def __init__(self,
                 mask="dm2_detector.mask",
                 num_frames=5,
                 path=None,
                 dm_num=2,
                 rotate=0,
                 fliplr=False,
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
        self.kwargs = kwargs

    def experiment(self):

        mask = "dm2_detector.mask" if self.dm_num == 2 else "dm1_detector.mask"

        with Accufiz("4d_accufiz", mask=mask) as four_d:
            # Reference image.
            reference_path = four_d.take_measurement(path=self.path,
                                                     filename="reference",
                                                     rotate=self.rotate,
                                                     fliplr=self.fliplr)

        with testbed.dm_controller() as dm:
            # Generate the 16 permutations of checkerboards, and add the commands to a list.
            for i in range(0, 952):
                file_name = "poke_actuator_{}".format(i)
                command = poke_command(i, amplitude=quantity(800, units.nanometers), dm_num=self.dm_num)

                dm.apply_shape(command, self.dm_num)
                with Accufiz("4d_accufiz", mask=mask) as four_d:
                    image_path = four_d.take_measurement(path=os.path.join(self.path, file_name),
                                                         num_frames=self.num_frames,
                                                         filename=file_name,
                                                         rotate=self.rotate,
                                                         fliplr=self.fliplr)

                    # Open fits files and subtract.
                    reference = fits.getdata(reference_path)
                    image = fits.getdata(image_path)

                    # Subtract the reference from image.
                    util.write_fits(reference - image, os.path.join(self.path, file_name + "_subtracted"))

                    # Save the DM_Command used.
                    command.export_fits(os.path.join(self.path, file_name))
