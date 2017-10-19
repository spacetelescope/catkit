from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import os

import numpy as np
# noinspection PyUnresolvedReferences
from builtins import *

from .modules import double_sine
from .Experiment import Experiment
from .. import util
from ..config import CONFIG_INI
from ..hardware import testbed
from ..hicat_types import units, quantity, SinSpecification, FpmPosition


class TakeDmPlateScaleData(Experiment):
    name = "Take DM Plate Scale Data"

    def __init__(self,
                 path=None,
                 bias=True,
                 flat_map=False,
                 coron_exposure_time=quantity(20, units.millisecond),
                 coron_nexps=3,
                 angle_range=range(70, 100, 10),
                 ncycles_range=np.arange(5.5, 17.5, .5),
                 peak_to_valley=quantity(30, units.nanometer),
                 phase=0):
        self.path = path
        self.bias = bias
        self.flat_map = flat_map
        self.coron_exposure_time = coron_exposure_time
        self.coron_nexps = coron_nexps
        self.angle_range = angle_range
        self.ncycles_range = ncycles_range
        self.peak_to_valley = peak_to_valley
        self.phase = phase

    def experiment(self):

        # Wait to set the path until the experiment starts (rather than the constructor)
        if self.path is None:
            self.path = util.create_data_path(suffix="dm_plate_scale")

        with testbed.laser_source() as laser:
            coron_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "coron_current")
            laser.set_current(coron_laser_current)

            for angle in self.angle_range:
                angles_path = os.path.join(self.path, "angle" + str(angle))
                for ncycle in self.ncycles_range:
                    sin_spec = SinSpecification(angle, ncycle, self.peak_to_valley, self.phase)
                    ncycle_path = os.path.join(angles_path, "ncycles" + str(ncycle))
                    double_sine.double_sin_remove_crossterm(sin_spec, self.bias, self.flat_map,
                                                            self.coron_exposure_time,
                                                            self.coron_nexps, FpmPosition.coron,
                                                            path=os.path.join(ncycle_path, "coron"))
