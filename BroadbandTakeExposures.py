from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences

from builtins import *
import logging
import os

from ..hardware.FilterWheelAssembly import FilterWheelAssembly

from .Experiment import Experiment
from ..hicat_types import *
from ..hardware.boston.commands import flat_command
from .. import util
from ..hardware import testbed
from ..hardware.thorlabs.ThorlabsFW102C import ThorlabsFW102C
from ..config import CONFIG_INI


class BroadbandTakeExposures(Experiment):
    name = "Broadband Take Exposures"
    log = logging.getLogger(__name__)

    def __init__(self,
                 filter_positions=None,
                 dm1_command_object=flat_command(bias=False, flat_map=True),  # Default flat with bias.
                 dm2_command_object=flat_command(bias=False, flat_map=True),  # Default flat with bias.
                 exposure_time=quantity(250, units.microsecond),
                 fpm=FpmPosition.direct,
                 num_exposures=5,
                 camera_type="imaging_camera",
                 exposure_set_name="direct",
                 pipeline=True,
                 path=None,
                 filename=None,
                 suffix=None,
                 **kwargs):
        """
        Takes a set of data with any camera, any DM command, any exposure time, etc.
        :param dm1_command_object: (DmCommand) DmCommand object to apply on a DM.
        :param exposure_time: (pint.quantity) Pint quantity for exposure time.
        :param num_exposures: (int) Number of exposures.
        :param step: (int) Step size to use for the motor positions (default is 10).
        :param path: (string) Path to save data.
        :param camera_type: (string) Camera type, maps to the [tested] section in the ini.
        :param position_list: (list) Postion(s) of the camera
        :param kwargs: Parameters for either the run_hicat_imaging function or the camera itself.
        """
        self.filter_positions = filter_positions
        self.dm1_command_object = dm1_command_object
        self.dm2_command_object = dm2_command_object
        self.exposure_time = exposure_time
        self.exposure_set_name = exposure_set_name
        self.fpm = fpm
        self.num_exposures = num_exposures
        self.camera_type = camera_type
        self.pipeline = pipeline
        self.path = path
        self.filename = filename
        self.suffix = suffix
        self.kwargs = kwargs

    def experiment(self):
        # Wait to set the path until the experiment starts (rather than the constructor)
        if self.path is None:
            suffix = "broadband" if self.suffix is None else "broadband_" + self.suffix
            self.path = util.create_data_path(suffix=suffix)

        util.setup_hicat_logging(self.path, "broadband")

        # Establish image type and set the FPM position and laser current.

        coron_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "coron_current")
        direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")

        # Take data at each filter wheel position.
        with testbed.laser_source() as laser, FilterWheelAssembly("filter_wheel_assembly") as filter_wheels:

            for position in self.filter_positions:
                filter_wheels.set_filters(position)
                metadata = MetaDataEntry("Filter Combination Name", "FILTERS", position, "Filter combination")
                # Reverse lookup.
                # filters_ini = {int(entry[1]): entry[0] for entry in CONFIG_INI.items("thorlabs_fw102c_2")
                #                if entry[0].startswith("filter_")}
                # filter_name = filters_ini[position]

                with testbed.dm_controller() as dm:
                    dm.apply_shape_to_both(self.dm1_command_object, self.dm2_command_object)

                    laser.set_current(direct_laser_current)
                    testbed.run_hicat_imaging(self.exposure_time, self.num_exposures, self.fpm,
                                              path=os.path.join(self.path, position),
                                              filename=self.filename,
                                              exposure_set_name=self.exposure_set_name,
                                              camera_type=self.camera_type,
                                              pipeline=self.pipeline,
                                              extra_metadata=metadata,
                                              **self.kwargs)
