from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import logging
from glob import glob

from ..Experiment import Experiment
from ...hardware.boston.commands import checkerboard_command, flat_command
from ...config import CONFIG_INI
from ... import util
from ...hicat_types import units, quantity, ImageCentering, MetaDataEntry
from ..modules.general import take_coffee_data_set


class CoffeeCheckerboardData(Experiment):
    """
    Creates a set of checkboard DM commands that will in effect poke every actuator in a more efficient way
    than poking 1 at a time.

    Args:
        amplitude (pint quantity): Amplitude to apply to each poke.
        direct_exp_time (pint quantity): Exposure time for the direct PSF data set.
        coron_exp_time (pint quantity): Exposure time for the coronographics data set.
        num_exposures (int): Number of exposures.
        path (string): Path to save data set. None will use the default.
        camera_type (string): Which camera to use, matches values in the ini file.
        focus_zernike_data_path (string): Defaults to high quality focus commands created in front of the 4d.
        centering (ImageCentering): Image centering algorithm for the coron data set.
        **kwargs:
    """

    name = "Coffee Checkerboard Data"
    log = logging.getLogger(__name__)

    def __init__(self,
                 amplitude=quantity(800, units.nanometer),
                 direct_exp_time=quantity(250, units.microsecond),
                 coron_exp_time=quantity(1, units.millisecond),
                 num_exposures=10,
                 path=None,
                 camera_type="imaging_camera",
                 focus_zernike_data_path="Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/focus/",
                 centering=ImageCentering.custom_apodizer_spots,
                 **kwargs):

        self.amplitude = amplitude
        self.direct_exp_time = direct_exp_time
        self.coron_exp_time = coron_exp_time
        self.num_exposures = num_exposures
        self.path = path
        self.camera_type = camera_type
        self.focus_zernike_data_path = focus_zernike_data_path
        self.centering = centering
        self.kwargs = kwargs

    def experiment(self):

        if self.path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "local_data_path")
            self.path = util.create_data_path(initial_path=central_store_path,
                                              suffix="checkerboard_" + self.camera_type)
        dm_num = 1
        flat_dm_command = flat_command(bias=False, flat_map=True)

        # Generate the 16 permutations of checkerboards, and add the commands to a list.
        for i in range(0, 4):
            for j in range(0, 4):
                file_name = "checkerboard_{}_{}_{}nm".format(i, j, self.amplitude.m)
                command = checkerboard_command(dm_num=dm_num, offset_x=i, offset_y=j,
                                               amplitude=self.amplitude,
                                               bias=False, flat_map=True)

                # Create metadata.
                metadata = [MetaDataEntry("offset_x", "offset_x", i, "Checkerboard offset x-axis")]
                metadata.append(MetaDataEntry("offset_y", "offset_y", j, "Checkerboard offset y-axis"))
                metadata.append(MetaDataEntry("amplitude",
                                              "amp",
                                              self.amplitude.to(units.nanometer).m,
                                              "Amplitude in nanometers"))

                # # Pure Focus Zernike loop.
                focus_zernike_command_paths = glob(self.focus_zernike_data_path + "/*p2v/*.fits")
                take_coffee_data_set(focus_zernike_command_paths,
                                     self.path,
                                     file_name,
                                     self.coron_exp_time,
                                     self.direct_exp_time,
                                     dm1_command_object=command,
                                     num_exposures=self.num_exposures,
                                     centering=self.centering,
                                     extra_metadata=metadata,
                                     **self.kwargs)


