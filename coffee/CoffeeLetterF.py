from glob import glob
import logging

from hicat.experiments.Experiment import Experiment
from catkit.hardware.boston import commands
from catkit.catkit_types import units, quantity, ImageCentering
from hicat.experiments.modules.general import take_coffee_data_set


class CoffeeLetterF(Experiment):
    """
    Applies a command to DM1 in the form of the letter F, and takes a COFFEE data set. Used for orientation.

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

    name = "Coffee Letter F"
    log = logging.getLogger(__name__)

    def __init__(self,
                 output_path=None,
                 diversity="focus",
                 num_exposures=10,
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(1, units.millisecond),
                 centering=ImageCentering.custom_apodizer_spots,
                 suffix = "coffee_letter_f",
                 **kwargs):

        super(CoffeeLetterF, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.diversity = diversity
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering
        self.kwargs = kwargs

    def experiment(self):

        # Diversity Zernike commands.
        diversity_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/dm2_commands/"
        if self.diversity == 'astigmatism_80nm':
            diversity_zernike_command_paths = glob(diversity_zernike_data_path + self.diversity + "/*/*.fits")
        else:
            diversity_zernike_command_paths = glob(diversity_zernike_data_path + self.diversity + "/*p2v/*.fits")

        # DM1 Letter F, DM2 chosen Zernike loop.
        letter_f = commands.poke_letter_f_command(dm_num=1)
        take_coffee_data_set(diversity_zernike_command_paths, self.output_path, "letter_f", self.coron_exp_time,
                             self.direct_exp_time, num_exposures=self.num_exposures,
                             dm1_command_object=letter_f, centering=self.centering, **self.kwargs)
