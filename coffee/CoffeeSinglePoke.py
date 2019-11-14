from glob import glob
import logging

from hicat.experiments.Experiment import Experiment
from catkit.hardware.boston import commands
from catkit.catkit_types import units, quantity, ImageCentering
from hicat.experiments.modules.general import take_coffee_data_set


class CoffeeSinglePoke(Experiment):
    """
    Pokes a single actuator, and takes a COFFEE data set. This is used to measure the interaction matrix

    Args:
        path (string): Path to save data set. None will use the default.
        diversity (string): What diversity to use on DM2. Defocus by default. Options can be found in
                            /astro/opticslab1/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/dm2_commands
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
                 output_path=None,
                 diversity="focus",
                 num_exposures=10,
                 actuator_num=595,
                 amplitude=quantity(32, units.nanometer),
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(1, units.millisecond),
                 centering=ImageCentering.custom_apodizer_spots,
                 suffix = "coffee_single_poke",
                 **kwargs):

        super(CoffeeSinglePoke, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.diversity = diversity
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering
        self.actuator_num = actuator_num
        self.amplitude = amplitude
        self.kwargs = kwargs

    def experiment(self):

        # Diversity Zernike commands for DM2.
        diversity_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/dm2_commands/"
        if self.diversity == 'astigmatism_80nm':
            diversity_zernike_command_paths = glob(diversity_zernike_data_path + self.diversity + "/*/*.fits")
        else:
            diversity_zernike_command_paths = glob(diversity_zernike_data_path + self.diversity + "/*p2v/*.fits")

        # DM1 poked actuator (actuator 595 is calibrated).
        poke_command_dm1 = commands.poke_command(self.actuator_num, dm_num=1, amplitude=self.amplitude)
        take_coffee_data_set(diversity_zernike_command_paths,
                             self.output_path,
                             "single_poke_actuator{}_amplitude{}_nm".format(self.actuator_num,self.amplitude.m),
                             self.coron_exp_time,
                             self.direct_exp_time,
                             num_exposures=self.num_exposures,
                             dm1_command_object=poke_command_dm1,
                             centering=self.centering,
                             **self.kwargs)
