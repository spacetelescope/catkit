from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import os
from astropy.io import fits

from hicat.hicat_types import MetaDataEntry
from .Experiment import Experiment
from ..hardware.boston.commands import checkerboard_command, flat_command
from ..hardware import testbed
from ..config import CONFIG_INI
from .. import util
from ..hicat_types import units, quantity, FpmPosition
from .modules.general import take_exposures


class TakeCheckerboardData(Experiment):
    name = "Take Checkerboard Data"

    def __init__(self,
                 amplitude=quantity(800, units.nanometer),
                 exposure_time=quantity(250, units.microsecond),
                 num_frames=2,
                 path=None,
                 camera_type="imaging_camera",
                 **kwargs):

        self.amplitude = amplitude
        self.exp_time = exposure_time
        self.num_frames = num_frames
        self.path = path
        self.camera_type = camera_type
        self.kwargs = kwargs

    def experiment(self):

        if self.path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "data_path")
            self.path = util.create_data_path(initial_path=central_store_path,
                                              suffix="checkerboard_" + self.camera_type)
        dm_num = 1
        with testbed.dm_controller() as dm:
            # Reference flat image.
            flat_dm_command = flat_command(bias=False, flat_map=True)
            reference_path = take_exposures(dm1_command_object=flat_dm_command,
                                            dm2_command_object=flat_dm_command,
                                            exposure_time=self.exp_time,
                                            num_exposures=1,
                                            camera_type=self.camera_type,
                                            coronograph=False,
                                            pipeline=True,
                                            path=self.path,
                                            filename="reference",
                                            exposure_set_name=None,
                                            suffix=None,
                                            **self.kwargs)

            # Generate the 16 permutations of checkerboards, and add the commands to a list.
            for i in range(0, 4):
                for j in range(0, 4):
                    file_name = "checkerboard_{}_{}_{}nm".format(i, j, self.amplitude)
                    command = checkerboard_command(dm_num=dm_num, offset_x=i, offset_y=j,
                                                   amplitude=self.amplitude,
                                                   bias=False, flat_map=True)
                    image_path = take_exposures(dm1_command_object=command,
                                                dm2_command_object=flat_dm_command,
                                                exposure_time=self.exp_time,
                                                num_exposures=self.num_frames,
                                                camera_type=self.camera_type,
                                                coronograph=False,
                                                pipeline=True,
                                                path=self.path,
                                                filename=file_name,
                                                exposure_set_name=None,
                                                suffix=None,
                                                **self.kwargs)

                    # Create metadata.
                    metadata = [MetaDataEntry("offset_x", "offset_x", i, "Checkerboard offset x-axis")]
                    metadata.append(MetaDataEntry("offset_y", "offset_y", j, "Checkerboard offset y-axis"))
                    metadata.append(MetaDataEntry("amplitude",
                                                  "amp",
                                                  self.amplitude.to(units.nanometer).m,
                                                  "Amplitude in nanometers"))

                    reference = fits.getdata(reference_path)
                    image = fits.getdata(image_path)
                    # Subtract the reference from image.
                    util.write_fits(reference - image,
                                    os.path.join(self.path, file_name + "_subtracted"),
                                    metadata=metadata)

                    # Save the DM_Command used.
                    command.export_fits(os.path.join(self.path, file_name))

            #return self.path
