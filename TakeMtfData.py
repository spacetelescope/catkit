from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from hicat import *
from hicat.experiments.Experiment import Experiment
from hicat.hardware.boston.flat_command import flat_command
from hicat.hardware.testbed import *
from hicat.hicat_types import *


class TakeMtfData(Experiment):

    def __initialize(self,
                     bias=True,
                     flat_map=False,
                     exposure_time=quantity(250, units.microsecond),
                     num_exposures=500):
        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures

    def experiment(self):

        # Create the date-time string to use as the experiment path.
        local_data_path = CONFIG_INI.get("optics_lab", "local_data_path")
        base_path = util.create_data_path(suffix="mtf_calibration", initial_path=local_data_path)

        # Create a flat dm command.
        flat_command_object, flat_file_name = flat_command(flat_map=self.flat_map,
                                                           bias=self.bias,
                                                           return_shortname=True)
        direct_exp_time = self.exposure_time
        num_exposures = self.num_exposures

        with laser_source() as laser:
            direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
            laser.set_current(direct_laser_current)

            with dm_controller() as dm:
                # Flat.
                dm.apply_shape(flat_command_object, 1)
                run_hicat_imaging(direct_exp_time, num_exposures, FpmPosition.direct, path=base_path,
                                  exposure_set_name="direct", filename=flat_file_name)
