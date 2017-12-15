from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import numpy as np
import os
from astropy.io import fits

from .Experiment import Experiment
from ..hardware.boston.commands import poke_letter_f_command, poke_command
from ..hardware import testbed
from ..hardware.FourDTechnology.Accufiz import Accufiz
from ..config import CONFIG_INI
from .. import util
from .. hicat_types import units, quantity


class Dm4dActuatorAnalysis(Experiment):
    name = "Dm 4d Actuator Analysis"

    def __init__(self,
                 actuators=[1],
                 amplitude_range=range(100,800,100),
                 amplitude_range_units = units.nanometer,
                 mask="dm2_detector.mask",
                 num_frames=2,
                 path=None,
                 filename=None,
                 dm_num=2,
                 rotate=180,
                 fliplr=False,
                 **kwargs):
        if path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "data_path")
            path = util.create_data_path(initial_path=central_store_path, suffix="4d")

        if filename is None:
            filename = "4d_"

        self.actuators = actuators
        self.amplitude_range = amplitude_range
        self.amplitude_range_units = amplitude_range_units
        self.mask = mask
        self.num_frames = num_frames
        self.path = path
        self.filename = filename
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.kwargs = kwargs

    def experiment(self):

        with Accufiz("4d_accufiz", mask=self.mask) as four_d:
            # Reference image.
            reference_path = four_d.take_measurement(path=self.path,
                                                     filename="reference",
                                                     rotate=self.rotate,
                                                     fliplr=self.fliplr)

        with testbed.dm_controller() as dm:

            for i in self.amplitude_range:
                file_name = "poke_amplitude_{}_nm".format(i)
                command = poke_command(self.actuators,
                                       amplitude=quantity(i, self.amplitude_range_units), dm_num=self.dm_num)

                dm.apply_shape(command, self.dm_num)
                with Accufiz("4d_accufiz", mask=self.mask) as four_d:
                    image_path = four_d.take_measurement(path=os.path.join(self.path, file_name),
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
