from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from glob import glob
import logging

from ..Experiment import Experiment
from ... import util
from ...hicat_types import units, quantity, ImageCentering
from ..modules.general import take_coffee_data_set


class CoffeeMultiAstigmatismFocus(Experiment):
    name = "Coffee Multi Astigmatism Focus"
    log = logging.getLogger(__name__)

    def __init__(self,
                 path=None,
                 num_exposures=10,
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(1, units.millisecond),
                 centering=ImageCentering.custom_apodizer_spots,
                 **kwargs):
        self.path = path
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering
        self.kwargs = kwargs

    def experiment(self):
        if self.path is None:
            suffix = "coffee_multi_astigmatism_focus"
            self.path = util.create_data_path(suffix=suffix)
            util.setup_hicat_logging(self.path, "coffee_multi_astigmatism_focus")

        # Multi astigmatsm+focus loop.
        multi_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/astigmastism_80nm"
        multi_zernike_command_paths = glob(multi_zernike_data_path + "/*/*.fits")

        take_coffee_data_set(multi_zernike_command_paths, self.path,
                             "astigmatism_80nm", self.coron_exp_time,
                             self.direct_exp_time, num_exposures=self.num_exposures,
                             centering=self.centering, **self.kwargs)
