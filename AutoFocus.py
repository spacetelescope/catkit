from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

from shutil import copyfile

# noinspection PyUnresolvedReferences
from builtins import *
import os
from glob import glob
import numpy as np

from .Experiment import Experiment
from .. import wolfram_wrappers
from ..hardware.boston.flat_command import flat_command
from .. import util
from ..hardware import testbed
from ..hicat_types import *
from ..config import CONFIG_INI


class AutoFocus(Experiment):
    name = "Auto Focus"

    def __init__(self,
                 bias=True,
                 flat_map=False,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=500,
                 position_list=np.arange(11.0, 13.7, step=.1),
                 path=None):
        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.position_list = position_list
        self.path = path

    def __collect_final_images(self):
        results = [y for x in os.walk(self.path) for y in glob(os.path.join(x[0], "*_cal.fits"))]
        for img in results:
            copyfile(img, os.path.join(self.path, os.path.basename(img)))

    def experiment(self):

        # Wait to set the path until the experiment starts (rather than the constructor)
        if self.path is None:
            self.path = util.create_data_path(suffix="focus")

        with testbed.laser_source() as laser:
            direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
            laser.set_current(direct_laser_current)

            with testbed.dm_controller() as dm:
                dm_command_object = flat_command(bias=True)
                dm.apply_shape(dm_command_object, 1)

                for i, position in enumerate(self.position_list):
                    init_motors = True if i == 0 else False
                    auto_exposure_time = True if i == 0 else False
                    with testbed.motor_controller(initialize_to_nominal=init_motors) as mc:
                        mc.absolute_move("motor_img_camera", position)
                    filename = "focus_" + str(int(position * 1000))
                    metadata = MetaDataEntry("Camera Position", "CAM_POS", position * 1000, "Position * 1000")
                    testbed.run_hicat_imaging(self.exposure_time, self.num_exposures, FpmPosition.direct, path=self.path,
                                              filename=filename, auto_exposure_time=auto_exposure_time,
                                              exposure_set_name="motor_" + str(int(position * 1000)),
                                              extra_metadata=metadata,
                                              raw_skip=0, use_background_cache=False,
                                              initialize_motors=False)

        self.__collect_final_images()
        print(wolfram_wrappers.run_auto_focus(self.path))
