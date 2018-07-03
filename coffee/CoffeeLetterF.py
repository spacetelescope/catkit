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


class CoffeeLetterF(Experiment):
    name = "Coffee Letter F"
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
            suffix = "coffee_letter_f"
            self.path = util.create_data_path(suffix=suffix)
            util.setup_hicat_logging(self.path, "coffee_letter_f")

        # Focus Zernike commands.
        focus_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/"
        focus_zernike_command_paths = glob(focus_zernike_data_path + "/*p2v/*.fits")


        # DM1 Letter F, DM2 focus loop.
        letter_f = commands.poke_letter_f_command(dm_num=1)
        take_coffee_data_set(focus_zernike_command_paths, self.path, "letter_f", self.coron_exp_time,
                             self.direct_exp_time, num_exposures=self.num_exposures,
                             dm1_command_object=letter_f, centering=self.centering)
