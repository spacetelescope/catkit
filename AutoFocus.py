import logging
import numpy as np

from hicat.experiments.Experiment import Experiment
from hicat.experiments.modules import auto_focus
from hicat.hicat_types import *


class AutoFocus(Experiment):
    name = "Auto Focus"
    log = logging.getLogger(__name__)

    def __init__(self,
                 bias=False,
                 flat_map=True,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=500,
                 position_list=np.arange(10.0, 16.0, step=0.1),
                 output_path=None,
                 camera_type="imaging_camera",
                 mtf_snr_threshold=100,
                 **kwargs):
        super(AutoFocus, self).__init__(output_path=output_path, **kwargs)
        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.position_list = position_list
        self.camera_type = camera_type
        self.mtf_snr_threshold = mtf_snr_threshold
        self.kwargs = kwargs

    def experiment(self):
        output_path = auto_focus.take_auto_focus_data(self.bias,
                                                      self.flat_map,
                                                      self.exposure_time,
                                                      self.num_exposures,
                                                      self.position_list,
                                                      self.output_path,
                                                      self.camera_type,
                                                      **self.kwargs)
        auto_focus.collect_final_images(output_path)
        auto_focus.auto_focus_mtf(output_path, self.position_list, self.mtf_snr_threshold)
