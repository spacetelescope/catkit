from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import numpy as np

from .Experiment import Experiment
from .modules import auto_focus
from .. import wolfram_wrappers
from ..hicat_types import *


class AutoFocus(Experiment):
    name = "Auto Focus"

    def __init__(self,
                 bias=True,
                 flat_map=False,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=500,
                 position_list=np.arange(11.0, 13.7, step=.1),
                 path=None,
                 camera_type="imaging_camera"):
        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.position_list = position_list
        self.path = path
        self.camera_type = camera_type

    def experiment(self):
        output_path = auto_focus.take_auto_focus_data(self.bias,
                                                      self.flat_map,
                                                      self.exposure_time,
                                                      self.num_exposures,
                                                      self.position_list,
                                                      self.path,
                                                      self.camera_type)
        auto_focus.collect_final_images(output_path)
        print(wolfram_wrappers.run_auto_focus(output_path))
