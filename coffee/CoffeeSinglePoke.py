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


class CoffeeSinglePoke(Experiment):
    """
    Pokes a single actuator, and takes a COFFEE data set. This is used to measure the interaction matrix

    Args:
        path (string): Path to save data set. None will use the default.
        num_exposures (int): Number of exposures.
        coron_exp_time (pint quantity): Exposure time for the coronographics data set.
        direct_exp_time (pint quantity): Exposure time for the direct PSF data set.
        centering (ImageCentering): Image centering algorithm for the coron data set.
        amplitude (pint quantity): requested PtV amplitude in nm calibrated on one actuator (32->10nm; 65->20mm; 160->50nm; 312->100nm)
        actuator_num (int): index of the actuator (1 through 952)s
        **kwargs: Keyword arguments passed into run_hicat_imaging()
    """

    name = "Coffee Single Poke"
    log = logging.getLogger(__name__)

    def __init__(self,
                 path=None,
                 num_exposures=10,
                 actuator_num=595,
                 amplitude=quantity(32, units.nanometer),
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(1, units.millisecond),
                 centering=ImageCentering.custom_apodizer_spots,
                 **kwargs):

        self.path = path
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering
        self.actuator_num = actuator_num
        self.amplitude = amplitude
        self.kwargs = kwargs

    def experiment(self):
        if self.path is None:
            suffix = "coffee_single_poke"
            self.path = util.create_data_path(suffix=suffix)
            util.setup_hicat_logging(self.path, "coffee_single_poke")

        # # Pure Focus Zernike loop.
        focus_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/focus/"
        focus_zernike_command_paths = glob(focus_zernike_data_path + "/*p2v/*.fits")

        # DM1 poked actuator (actuator 595 is calibrated).
        poke_command_dm1 = commands.poke_command(self.actuator_num, dm_num=1, amplitude=self.amplitude)
        take_coffee_data_set(focus_zernike_command_paths, self.path, "single_poke_actuator{}_amplitude{}_nm".format(self.actuator_num,self.amplitude.m), self.coron_exp_time,
                             self.direct_exp_time, num_exposures=self.num_exposures,
                             dm1_command_object=poke_command_dm1, centering=self.centering, **self.kwargs)
