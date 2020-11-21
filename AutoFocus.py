import logging
import numpy as np

from hicat.experiments.Experiment import Experiment
from hicat.experiments.modules import auto_focus
from hicat.config import CONFIG_INI
from catkit.catkit_types import quantity, units


class AutoFocus(Experiment):
    name = "Auto Focus"
    log = logging.getLogger(__name__)

    def __init__(self,
                 bias=False,
                 flat_map=True,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=20,
                 position_list=None,
                 output_path=None,
                 camera_type="imaging_camera",
                 mtf_snr_threshold=None,
                 **kwargs):
        super().__init__(output_path=output_path, **kwargs)

        if position_list is None:
            start_pos = CONFIG_INI.getfloat("calibration", "auto_focus_start_position")
            end_pos = CONFIG_INI.getfloat("calibration", "auto_focus_end_position")
            step_size = CONFIG_INI.getfloat("calibration", "auto_focus_position_step_size")
            position_list = np.arange(start_pos, end_pos, step_size)
        if mtf_snr_threshold is None:
            mtf_snr_threshold = CONFIG_INI.getint("calibration", "auto_focus_mtf_snr_thrshold")

        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.position_list = position_list
        self.camera_type = camera_type
        self.mtf_snr_threshold = mtf_snr_threshold
        self.kwargs = kwargs

        if 'raw_skip' not in kwargs:
            # Only save 1 representative raw image per position, not all of them
            kwargs['raw_skip'] = self.num_exposures + 1

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
