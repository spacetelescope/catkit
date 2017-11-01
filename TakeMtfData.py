from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from .Experiment import Experiment
from ..hardware.boston.commands import flat_command
from ..hardware import testbed
from ..hicat_types import units, quantity, FpmPosition
from .. import util
from ..config import CONFIG_INI
from ..wolfram_wrappers import run_mtf


class TakeMtfData(Experiment):
    name = "Take MTF Data"

    def __init__(self,
                 bias=True,
                 flat_map=False,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=100,
                 path=None,
                 camera_type="imaging_camera"):
        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.path = path
        self.camera_type = camera_type

    def experiment(self):
        # Wait to set the path until the experiment starts (rather than the constructor).
        if self.path is None:
            self.path = util.create_data_path(suffix="mtf_calibration")

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
                cal_file_path = testbed.run_hicat_imaging(direct_exp_time, num_exposures, FpmPosition.direct,
                                                          path=self.path, exposure_set_name="direct",
                                                          filename=flat_file_name, camera_type=self.camera_type)
        ps_wo_focus, ps_w_focus, focus = run_mtf(cal_file_path)
        print(ps_wo_focus, ps_w_focus, focus)
