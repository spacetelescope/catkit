from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from glob import glob
import logging

from ..Experiment import Experiment
from ...hardware.boston import commands
from hicat.hardware.boston.sin_command import sin_command
from ... import util
from ...hicat_types import units, quantity, ImageCentering, SinSpecification
from ..modules.general import take_coffee_data_set

class CoffeeRipple(Experiment):
    """
    Creates a sine ripple and takes a COFFEE data set.

    Args:
        path (string): Path to save data set. None will use the default.
        num_exposures (int): Number of exposures.
        coron_exp_time (pint quantity): Exposure time for the coronographics data set.
        direct_exp_time (pint quantity): Exposure time for the direct PSF data set.
        centering (ImageCentering): Image centering algorithm for the coron data set.
        amplitude (pint quantity): PtV amplitude in nm
        phase (real): phase of the phase ripple (used to make sine vs. cosine)
        ncycle (int): number of cycles accross the DM for the phase ripple
        **kwargs: Keyword arguments passed into run_hicat_imaging()
    """

    name = "Coffee Ripple"
    log = logging.getLogger(__name__)

    def __init__(self,
                 path=None,
                 num_exposures=10,
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(1, units.millisecond),
                 centering=ImageCentering.custom_apodizer_spots,
                 ncycle=10,
                 phase = 0,
                 amplitude = quantity(100,units.nanometer),
                 **kwargs):

        self.path = path
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering
        self.kwargs = kwargs
        self.ncycle = ncycle
        self.phase = phase
        self.amplitude = amplitude

    def experiment(self):
        if self.path is None:
            suffix = "coffee_ripple"
            self.path = util.create_data_path(suffix=suffix)
            util.setup_hicat_logging(self.path, "coffee_ripple")

        # # Pure Focus Zernike loop.
        focus_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/focus/"
        focus_zernike_command_paths = glob(focus_zernike_data_path + "/*p2v/*.fits")

        # DM1 phase ripple
        horizontal = SinSpecification(0, self.ncycle, self.amplitude,self.phase)
        ripple_command_dm1 = sin_command(horizontal,flat_map=True)
        take_coffee_data_set(focus_zernike_command_paths, self.path, "ripple", self.coron_exp_time,
                             self.direct_exp_time, num_exposures=self.num_exposures,
                             dm1_command_object=ripple_command_dm1, centering=self.centering, **self.kwargs)
