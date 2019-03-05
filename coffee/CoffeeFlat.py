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


class CoffeeFlat(Experiment):
    """
    DM1 is set to it's flatmap, and a COFFEE data set is taken.

    Args:
        path (string): Path to save data set. None will use the default.
        diversity (string): What diversity to use on DM2. Defocus by default. Options can be found in
                            /astro/opticslab1/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/dm2_commands
        num_exposures (int): Number of exposures.
        coron_exp_time (pint quantity): Exposure time for the coronographics data set.
        direct_exp_time (pint quantity): Exposure time for the direct PSF data set.
        centering (ImageCentering): Image centering algorithm for the coron data set.
        pipeline (bool): Flag that determines whether to run the realtime data pipeline.
        **kwargs: Keyword arguments passed into run_hicat_imaging()
    """

    name = "Coffee Flat"
    log = logging.getLogger(__name__)

    def __init__(self,
                 path=None,
                 diversity="focus",
                 num_exposures=10,
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(1, units.millisecond),
                 centering=ImageCentering.custom_apodizer_spots,
                 pipeline=True,
                 **kwargs):

        self.path = path
        self.diversity = diversity
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering
        self.pipeline = pipeline
        self.kwargs = kwargs

    def experiment(self):
        if self.path is None:
            suffix = "coffee_flat"
            self.path = util.create_data_path(suffix=suffix)
            util.setup_hicat_logging(self.path, "coffee_flat")

        # Diversity Zernike commands on DM2, with a flat applied to DM1.
        diversity_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/dm2_commands/"
        if self.diversity == 'astigmatism_80nm':
            diversity_zernike_command_paths = glob(diversity_zernike_data_path + self.diversity + "/*/*.fits")
        else:
            diversity_zernike_command_paths = glob(diversity_zernike_data_path + self.diversity + "/*p2v/*.fits")

        take_coffee_data_set(diversity_zernike_command_paths,
                             self.path,
                             "flat",
                             self.coron_exp_time,
                             self.direct_exp_time,
                             num_exposures=self.num_exposures,
                             centering=self.centering,
                             pipeline=self.pipeline,
                             **self.kwargs)
