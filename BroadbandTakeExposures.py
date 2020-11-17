import logging
import os

from catkit.hardware.FilterWheelAssembly import FilterWheelAssembly

from hicat.experiments.Experiment import Experiment
from hicat.experiments.modules import iris_ao
from catkit.catkit_types import * # OHNO
from catkit.hardware.boston.commands import flat_command
from hicat.hardware import testbed
from catkit.hardware.thorlabs.ThorlabsFW102C import ThorlabsFW102C
from hicat.config import CONFIG_INI


class BroadbandTakeExposures(Experiment):
    name = "Broadband Take Exposures"
    log = logging.getLogger(__name__)

    def __init__(self,
                 broadband_filter_set="bb_direct_set",
                 dm1_command_object=flat_command(bias=False, flat_map=True),  # Default flat with bias.
                 dm2_command_object=flat_command(bias=False, flat_map=True),  # Default flat with bias.
                 exposure_time=quantity(250, units.microsecond),
                 fpm=FpmPosition.direct,
                 num_exposures=5,
                 camera_type="imaging_camera",
                 pipeline=True,
                 output_path=None,
                 filename=None,
                 suffix='broadband',
                 **kwargs):
        """
        Takes a set of data with any camera, any DM command, any exposure time, etc.
        :param dm1_command_object: (DmCommand) DmCommand object to apply on a DM.
        :param exposure_time: (pint.quantity) Pint quantity for exposure time.
        :param num_exposures: (int) Number of exposures.
        :param step: (int) Step size to use for the motor positions (default is 10).
        :param output_path: (string) Path to save data.
        :param camera_type: (string) Camera type, maps to the [tested] section in the ini.
        :param position_list: (list) Postion(s) of the camera
        :param kwargs: Parameters for either the run_hicat_imaging function or the camera itself.
        """
        super(BroadbandTakeExposures, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.broadband_filter_set = broadband_filter_set
        self.dm1_command_object = dm1_command_object
        self.dm2_command_object = dm2_command_object
        self.exposure_time = exposure_time
        self.fpm = fpm
        self.num_exposures = num_exposures
        self.camera_type = camera_type
        self.pipeline = pipeline
        self.filename = filename
        self.kwargs = kwargs

    def experiment(self):

        with testbed.dm_controller() as dm, \
                testbed.iris_ao() as iris_dm:
            dm.apply_shape_to_both(self.dm1_command_object, self.dm2_command_object)
            iris_dm.apply_shape(iris_ao.flat_command())

            testbed.run_hicat_imaging_broadband(self.broadband_filter_set,
                                                self.exposure_time, self.num_exposures, self.fpm,
                                                path=self.output_path,
                                                filename=self.filename,
                                                camera_type=self.camera_type,
                                                pipeline=self.pipeline,
                                                **self.kwargs)
