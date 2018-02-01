from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from glob import glob
import logging

from .Experiment import Experiment
from ..hardware.boston import commands
from ..hicat_types import units, quantity, ImageCentering
from .. import util
from .modules.general import take_exposures_dm_commands


class CoffeeDataCollection(Experiment):
    name = "Coffee Data Collection"
    log = logging.getLogger(__name__)

    def __init__(self,
                 num_exposures=10,
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(1, units.millisecond),
                 centering=ImageCentering.custom_apodizer_spots):
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering

    def experiment(self):
        local_path = util.create_data_path(suffix="coffee_data")

        # # Pure Focus Zernike loop.
        focus_zernike_data_path = "z:/Testbeds/hicat_dev/data_vault/dm2_calibration/2018-01-21T09-34-00_4d_zernike_loop_focus/"
        focus_zernike_command_paths = glob(focus_zernike_data_path + "/*p2v/*.fits")
        take_exposures_dm_commands(focus_zernike_command_paths, local_path, "focus", self.coron_exp_time,
                                   self.direct_exp_time,
                                   num_exposures=self.num_exposures,
                                   centering=self.centering)

        # Multi astigmatsm+focus loop.
        multi_zernike_data_path = "z:/Testbeds/hicat_dev/data_vault/dm2_calibration/2018-01-21T15-44-32_4d_multi_zernike_loop_astigmatism_45_focus/astigmatism_45_40_nm/"
        multi_zernike_command_paths = glob(multi_zernike_data_path + "/*/*.fits")

        take_exposures_dm_commands(multi_zernike_command_paths, local_path,
                                   "astigmatism45_40nm_and_focus", self.coron_exp_time,
                                   self.direct_exp_time, num_exposures=self.num_exposures,
                                   centering=self.centering)

        # DM1 Letter F, DM2 focus loop.
        letter_f = commands.poke_letter_f_command(dm_num=1)
        take_exposures_dm_commands(focus_zernike_command_paths, local_path, "letter_f_and_focus", self.coron_exp_time,
                                   self.direct_exp_time, list_of_paths=True, num_exposures=self.num_exposures,
                                   dm1_command_object=letter_f, centering=self.centering)

        # DM1 OFF and DM2 focus loop.
        take_exposures_dm_commands(focus_zernike_command_paths, local_path, "focus_dm1_off", self.coron_exp_time,
                                   self.direct_exp_time, dm1_command_object=commands.flat_command(bias=False, flat_map=False),
                                   num_exposures=self.num_exposures, centering=self.centering)
