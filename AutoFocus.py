from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import logging
import numpy as np

from .Experiment import Experiment
from .modules import auto_focus
from .. import wolfram_wrappers
from ..hicat_types import *


class AutoFocus(Experiment):
    name = "Auto Focus"
    log = logging.getLogger(__name__)

    def __init__(self,
                 bias=False,
                 flat_map=True,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=500,
                 position_list=np.arange(11.0, 13.7, step=.1),
                 path=None,
                 camera_type="imaging_camera",
                 **kwargs):
        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.position_list = position_list
        self.path = path
        self.camera_type = camera_type
        self.kwargs = kwargs

    def experiment(self):
        output_path = auto_focus.take_auto_focus_data(self.bias,
                                                      self.flat_map,
                                                      self.exposure_time,
                                                      self.num_exposures,
                                                      self.position_list,
                                                      self.path,
                                                      self.camera_type,
                                                      **self.kwargs)
        auto_focus.collect_final_images(output_path)
        self.log.info(wolfram_wrappers.run_auto_focus(output_path))
