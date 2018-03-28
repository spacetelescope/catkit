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
from .modules.general import take_coffee_data_set


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
        focus_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee_commands/focus"
        focus_zernike_command_paths = glob(focus_zernike_data_path + "/*p2v/*.fits")
        take_coffee_data_set(focus_zernike_command_paths,
                             local_path,
                             "focus",
                             self.coron_exp_time,
                             self.direct_exp_time,
                             num_exposures=self.num_exposures,
                             centering=self.centering,
                             raw_skip=100)

        # Multi astigmatsm+focus loop.
        # multi_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee_commands/astigmastism_80nm"
        # multi_zernike_command_paths = glob(multi_zernike_data_path + "/*/*.fits")
        #
        # take_coffee_data_set(multi_zernike_command_paths, local_path,
        #                      "astigmatism_80nm", self.coron_exp_time,
        #                      self.direct_exp_time, num_exposures=self.num_exposures,
        #                      centering=self.centering)

        # DM1 Letter F, DM2 focus loop.
        # letter_f = commands.poke_letter_f_command(dm_num=1)
        # take_coffee_data_set(focus_zernike_command_paths, local_path, "letter_f", self.coron_exp_time,
        #                      self.direct_exp_time, num_exposures=self.num_exposures,
        #                      dm1_command_object=letter_f, centering=self.centering)

        # DM1 Center 4 actuators.
        # actuators = [458, 459, 492, 493]
        # center_command_dm1 = commands.poke_command(actuators, dm_num=1, amplitude=quantity(250, units.nanometers))
        # take_coffee_data_set(focus_zernike_command_paths, local_path, "center_poke", self.coron_exp_time,
        #                      self.direct_exp_time, num_exposures=self.num_exposures,
        #                      dm1_command_object=center_command_dm1, centering=self.centering)


        # DM1 OFF and DM2 focus loop.
        # take_coffee_data_set(focus_zernike_command_paths, local_path, "focus_dm1_off", self.coron_exp_time,
        #                      self.direct_exp_time, dm1_command_object=commands.flat_command(bias=False, flat_map=False),
        #                      num_exposures=self.num_exposures, centering=self.centering)
