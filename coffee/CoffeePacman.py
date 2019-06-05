from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from glob import glob
import logging
import os

from ..Experiment import Experiment
from ...hardware.boston import DmCommand
from ... import util
from ...hicat_types import units, quantity, ImageCentering
from ..modules.general import take_coffee_data_set


class CoffeePacman(Experiment):
    """
    Takes COFFEE data sets for an set of PACMAN images based on an animated GIF.


    Args:
        path (string): Path to save data set. None will use the default.
        diversity (string): What diversity to use on DM2. Defocus by default. Options can be found in
                            /astro/opticslab1/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/dm2_commands
        num_exposures (int): Number of exposures.
        coron_exp_time (pint quantity): Exposure time for the coronographics data set.
        direct_exp_time (pint quantity): Exposure time for the direct PSF data set.
        centering (ImageCentering): Image centering algorithm for the coron data set.
        **kwargs: Keyword arguments passed into run_hicat_imaging()
    """

    name = "Coffee Pacman (nom nom nom)"
    log = logging.getLogger(__name__)

    def __init__(self,
                 output_path=None,
                 diversity="focus",
                 num_exposures=10,
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(1, units.millisecond),
                 centering=ImageCentering.custom_apodizer_spots,
                 suffix = "coffee_pacman",
                 **kwargs):

        super(CoffeePacman, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.diversity = diversity
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering
        self.kwargs = kwargs

    def experiment(self):

        # Diversity Zernike commands for DM2.
        diversity_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/dm2_commands/"
        if self.diversity == 'astigmatism_80nm':
            diversity_zernike_command_paths = glob(diversity_zernike_data_path + self.diversity + "/*/*.fits")
        else:
            diversity_zernike_command_paths = glob(diversity_zernike_data_path + self.diversity + "/*p2v/*.fits")

        # Pacman Commands for DM1.
        pacman_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/dm1_commands/pacman/"
        pacman_command_paths = glob(pacman_data_path + "/dm_command/*/dm_command_2d_noflat.fits")
        pacman_command_paths.sort()

        for i, command_path in enumerate(pacman_command_paths):
            dm1_command_object = DmCommand.load_dm_command(command_path, flat_map=True)
            take_coffee_data_set(diversity_zernike_command_paths,
                                 os.path.join(self.output_path, "pacman"),
                                 "gif_frame_" + str(i),
                                 self.coron_exp_time,
                                 self.direct_exp_time,
                                 dm1_command_object=dm1_command_object,
                                 num_exposures=self.num_exposures,
                                 centering=self.centering,
                                 **self.kwargs)
