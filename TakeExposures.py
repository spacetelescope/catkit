from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import logging

from .Experiment import Experiment
from ..hicat_types import *
from .. import util
from ..hardware import testbed
from ..config import CONFIG_INI
from ..hardware.boston.commands import flat_command


class TakeExposures(Experiment):
    name = "Take Exposures"

    def __init__(self,
                 dm_command_object=flat_command(True, False),  # Default flat with bias.
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=5,
                 camera_type="imaging_camera",
                 coronograph=False,
                 pipeline=True,
                 path=None,
                 exposure_set_name=None,
                 filename=None,
                 **kwargs):
        """
        Takes a set of data with any camera, any DM command, any exposure time, etc.
        :param dm_command_object: (DmCommand) DmCommand object to apply on a DM.
        :param exposure_time: (pint.quantity) Pint quantity for exposure time.
        :param num_exposures: (int) Number of exposures.
        :param step: (int) Step size to use for the motor positions (default is 10).
        :param path: (string) Path to save data.
        :param camera_type: (string) Camera type, maps to the [tested] section in the ini.
        :param position_list: (list) Postion(s) of the camera
        :param kwargs: Parameters for either the run_hicat_imaging function or the camera itself.
        """
        self.dm_command_object = dm_command_object
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.camera_type = camera_type
        self.coronograph = coronograph
        self.pipeline = pipeline
        self.path = path
        self.exposure_set_name = exposure_set_name
        self.filename = filename
        self.kwargs = kwargs

    def experiment(self):
        take_exposures(self.dm_command_object,
                       self.exposure_time,
                       self.num_exposures,
                       self.camera_type,
                       self.coronograph,
                       self.pipeline,
                       self.path,
                       self.filename,
                       self.exposure_set_name,
                       **self.kwargs)


def take_exposures(dm_command_object,
                   exposure_time,
                   num_exposures,
                   camera_type,
                   coronograph,
                   pipeline,
                   path,
                   filename,
                   exposure_set_name,
                   **kwargs):

    # Wait to set the path until the experiment starts (rather than the constructor)
    if path is None:
        path = util.create_data_path(suffix="take_exposures_data")
        util.setup_hicat_logging(path, "take_exposures_data", level=logging.WARNING)


    # Establish image type and set the FPM position and laser current
    if coronograph:
        fpm_position = FpmPosition.coron
        laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "coron_current")
        if exposure_set_name is None:
            exposure_set_name = "coron"
    else:
        fpm_position = FpmPosition.direct
        laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
        if exposure_set_name is None:
            exposure_set_name = "direct"

    # Take data
    with testbed.laser_source() as laser:
        laser.set_current(laser_current)

        if dm_command_object:
            with testbed.dm_controller() as dm:
                dm.apply_shape(dm_command_object, dm_command_object.dm_num)
                testbed.run_hicat_imaging(exposure_time, num_exposures, fpm_position, path=path,
                                          filename=filename,
                                          exposure_set_name=exposure_set_name,
                                          camera_type=camera_type,
                                          pipeline=pipeline,
                                          **kwargs)
        else:
            testbed.run_hicat_imaging(exposure_time, num_exposures, fpm_position, path=path,
                                      filename=filename,
                                      exposure_set_name=exposure_set_name,
                                      camera_type=camera_type,
                                      pipeline=pipeline,
                                      **kwargs)

    return path
