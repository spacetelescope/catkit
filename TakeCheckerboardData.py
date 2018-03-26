from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import os
from glob import glob
from astropy.io import fits

from hicat import dm_calibration_util
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
                 amplitude=quantity(800, units.nanometer),
                 num_frames=2,
                 path=None,
                 camera_type="imaging_camera",
                 **kwargs):

        self.amplitude = amplitude
        self.num_frames = num_frames
        self.path = path
        self.camera_type = camera_type
        self.kwargs = kwargs

    def experiment(self):

        if self.path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "data_path")
            self.path = util.create_data_path(initial_path=central_store_path,
                                              suffix="checkerboard_" + self.camera_type)

        with testbed.dm_controller() as dm:

            # Reference flat image.


            # Generate the 16 permutations of checkerboards, and add the commands to a list.
            for i in range(0, 4):
                for j in range(0, 4):
                    file_name = "checkerboard_{}_{}_{}nm".format(i, j, self.amplitude)
                    command = checkerboard_command(dm_num=1, offset_x=i, offset_y=j,
                                                   amplitude=self.amplitude,
                                                   bias=False, flat_map=True)
                    dm.apply_shape(command, 1)
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
                        metadata.append(MetaDataEntry("amplitude",
                                                      "amp",
                                                      self.amplitude.to(units.nanometer).m,
                                                      "Amplitude in nanometers"))


        files_path = glob(os.path.join(self.path, file_name.split("_")[0] + "*_subtracted.fits"))
        dm_calibration_util.create_actuator_index(self.dm_num, path=self.path,
                                                  files=files_path,
                                                  reffiles=reference_path,
                                                  show_plot=self.show_plot,
                                                  overwrite_csv=self.overwrite_csv)
