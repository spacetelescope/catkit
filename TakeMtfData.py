from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from .Experiment import Experiment
from ..hardware.boston.flat_command import flat_command
from ..hardware import testbed
from ..hicat_types import units, quantity, FpmPosition
from .. import util
from ..config import CONFIG_INI


class TakeMtfData(Experiment):
    def __init__(self,
                 bias=True,
                 flat_map=False,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=500,
                 path=None):
        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        if path is None:
            path = util.create_data_path(suffix="mtf_calibration")
        self.path = path

    def experiment(self):
        # Create a flat dm command.
        flat_command_object, flat_file_name = flat_command(flat_map=self.flat_map,
                                                           bias=self.bias,
                                                           return_shortname=True)
        direct_exp_time = self.exposure_time
        num_exposures = self.num_exposures

        with testbed.laser_source() as laser:
            direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
            laser.set_current(direct_laser_current)

            with testbed.dm_controller() as dm:
                # Flat.
                dm.apply_shape(flat_command_object, 1)
                testbed.run_hicat_imaging(direct_exp_time, num_exposures, FpmPosition.direct, path=self.path,
                                          exposure_set_name="direct", filename=flat_file_name)
