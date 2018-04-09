from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import numpy as np
import logging
import os
import csv
from astropy.io import fits

from .Experiment import Experiment
from ..hardware.boston.commands import poke_letter_f_command, poke_command, flat_command
from ..hardware.boston import DmCommand
from ..hardware import testbed
from ..hardware.FourDTechnology.Accufiz import Accufiz
from ..config import CONFIG_INI
from .. import util
from ..hicat_types import units, quantity
from .. import dm_calibration_util


class Take4dImageDmCommand(Experiment):
    name = "Take 4d Image DM Command"
    log = logging.getLogger(__name__)

    def __init__(self,
                 mask="dm1_detector.mask",
                 num_frames=2,
                 path=None,
                 filename=None,
                 dm_num=1,
                 rotate=180,
                 fliplr=False,
                 command=flat_command(flat_map=True),
                 suffix="",
                 **kwargs):

        if filename is None:
            filename = "4d_"

        self.mask = mask
        self.num_frames = num_frames
        self.path = path
        self.filename = filename
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.command = command
        self.suffix = suffix
        self.kwargs = kwargs

    def experiment(self):

        if self.path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "data_path")
            self.path = util.create_data_path(initial_path=central_store_path, suffix="Take4dImageDmCommand" + self.suffix)

        # Read in the actuator map into a dictionary.
        map_file_name = "actuator_map_dm1.csv" if self.dm_num == 1 else "actuator_map_dm2.csv"
        repo_path = util.find_repo_location()
        mask_path = os.path.join(repo_path, "hicat", "hardware", "FourDTechnology", map_file_name)
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
                image_path = four_d.take_measurement(path=os.path.join(self.path, file_name),
                                                     filename=file_name,
                                                     rotate=self.rotate,
                                                     num_frames=self.num_frames,
                                                     fliplr=self.fliplr)

                # Save the DM_Command used.
                self.command.export_fits(os.path.join(self.path, file_name))
