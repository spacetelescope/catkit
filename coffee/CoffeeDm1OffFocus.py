from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from glob import glob
import logging

from ..Experiment import Experiment
from ...hardware.boston import commands
from ... import util
from ...hicat_types import units, quantity, ImageCentering
from ..modules.general import take_coffee_data_set


class CoffeeDm1OffFocus(Experiment):
    name = "Coffee Dm1 Off Focus"
    log = logging.getLogger(__name__)

    def __init__(self,
                 path=None,
                 num_exposures=10,
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(1, units.millisecond),
                 centering=ImageCentering.custom_apodizer_spots):
        self.path = path
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering

    def experiment(self):
        if self.path is None:
            suffix = "coffee_dm1_off_focus"
            self.path = util.create_data_path(suffix=suffix)
            util.setup_hicat_logging(self.path, "coffee_dm1_off_focus")

        # # Pure Focus Zernike loop.
        focus_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/"
        focus_zernike_command_paths = glob(focus_zernike_data_path + "/*p2v/*.fits")

        # DM1 OFF and DM2 focus loop.
        take_coffee_data_set(focus_zernike_command_paths, self.path, "focus_dm1_off", self.coron_exp_time,
                             self.direct_exp_time, dm1_command_object=commands.flat_command(bias=False, flat_map=False),
                             num_exposures=self.num_exposures, centering=self.centering)
