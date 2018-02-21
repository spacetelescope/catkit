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


class TestPrDmCommands(Experiment):
    name = "PR Test DM Command Data Collection"
    log = logging.getLogger(__name__)

    def __init__(self, commands_path,
                 num_exposures=10,
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(1, units.millisecond),
                 centering=ImageCentering.custom_apodizer_spots):
        self.commands_path = commands_path
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering

    def experiment(self):
        local_path = util.create_data_path(suffix="test_pr_dm_data")

        # DM1 Flat, DM2 PR WF correction command.
        take_exposures_dm_commands(self.commands_path, local_path, "pr_flats", self.coron_exp_time,
                                   self.direct_exp_time, list_of_paths=True,
                                   num_exposures=self.num_exposures,
                                   centering=self.centering)

        # DM1 Flat, DM2 Flat.
        dm2_command = commands.flat_command(bias=False, flat_map=True, dm_num=2,
                                            return_shortname=True)
        take_exposures_dm_commands([dm2_command],
                                   local_path, "pr_flats", self.coron_exp_time,
                                   self.direct_exp_time, list_of_paths=False,
                                   num_exposures=self.num_exposures,
                                   centering=self.centering)
