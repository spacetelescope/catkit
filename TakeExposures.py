import logging

from hicat.experiments.Experiment import Experiment
from hicat.hicat_types import * # AGAIN, OHNO
from catkit.hardware.boston.commands import flat_command
from hicat.experiments.modules.general import take_exposures
from hicat import util


class TakeExposures(Experiment):
    name = "Take Exposures"
    log = logging.getLogger(__name__)

    def __init__(self,
                 dm1_command_object=flat_command(bias=False, flat_map=True),  # Default flat with bias.
                 dm2_command_object=flat_command(bias=False, flat_map=True),  # Default flat with bias.
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=5,
                 camera_type="imaging_camera",
                 coronograph=False,
                 pipeline=True,
                 output_path=None,
                 exposure_set_name=None,
                 filename=None,
                 suffix='take_exposures',
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
        super(TakeExposures,  self).__init__(output_path=output_path, suffix=suffix)
        self.dm1_command_object = dm1_command_object
        self.dm2_command_object = dm2_command_object
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.camera_type = camera_type
        self.coronograph = coronograph
        self.pipeline = pipeline
        self.exposure_set_name = exposure_set_name
        self.filename = filename
        self.kwargs = kwargs

    def experiment(self):
        take_exposures(self.dm1_command_object,
                       self.dm2_command_object,
                       self.exposure_time,
                       self.num_exposures,
                       self.camera_type,
                       self.coronograph,
                       self.pipeline,
                       self.output_path,
                       self.filename,
                       self.exposure_set_name,
                       self.suffix,
                       **self.kwargs)
