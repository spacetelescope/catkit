from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import logging

from .Experiment import Experiment
from ..hardware.boston.commands import flat_command
from ..hardware import testbed
from ..hicat_types import units, quantity, FpmPosition
from .. import util
from ..config import CONFIG_INI
from ..wolfram_wrappers import run_mtf


class TakeMtfData(Experiment):
    name = "Take MTF Data"
    log = logging.getLogger(__name__)

    def __init__(self,
                 bias=False,
                 flat_map=True,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=100,
                 output_path=None,
                 camera_type="imaging_camera",
                 suffix="mtf_calibration",
                 **kwargs):
        super(TakeMtfData, self).__init__(output_path=output_path, suffix=suffix, **kwargs)

        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.camera_type = camera_type
        self.kwargs = kwargs

    def experiment(self):

        # Create a flat dm command.
        flat_command_object1, flat_file_name = flat_command(flat_map=self.flat_map,
                                                           bias=self.bias,
                                                           return_shortname=True,
                                                           dm_num=1)

        flat_command_object2, flat_file_name = flat_command(flat_map=self.flat_map,
                                                           bias=self.bias,
                                                           return_shortname=True,
                                                           dm_num=2)
        direct_exp_time = self.exposure_time
        num_exposures = self.num_exposures

        with testbed.laser_source() as laser:
            direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
            laser.set_current(direct_laser_current)

            with testbed.dm_controller() as dm:
                # Flat.
                dm.apply_shape_to_both(flat_command_object1, flat_command_object2)
                cal_file_path = testbed.run_hicat_imaging(direct_exp_time, num_exposures, FpmPosition.direct,
                                                          path=self.output_path, exposure_set_name="direct",
                                                          filename=flat_file_name, camera_type=self.camera_type,
                                                          simulator=False,
                                                          **self.kwargs)
        ps_wo_focus, ps_w_focus, focus = run_mtf(cal_file_path)
        self.log.info("ps_wo_focus=" + str(ps_wo_focus) + " ps_w_focus=" +str(ps_w_focus) + " focus=" +str(focus) )
