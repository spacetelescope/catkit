from glob import glob
import logging

from hicat.experiments.Experiment import Experiment
from catkit.hardware.boston import commands
from hicat.hicat_types import units, quantity, ImageCentering
from hicat.experiments.modules.general import take_coffee_data_set


class CoffeeDm1OffFocus(Experiment):
    name = "Coffee Dm1 Off Focus"
    log = logging.getLogger(__name__)

    def __init__(self,
                 output_path=None,
                 num_exposures=10,
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(1, units.millisecond),
                 centering=ImageCentering.custom_apodizer_spots,
                 suffix = "coffee_dm1_off_focus",
                 **kwargs):
        """
        Takes a coffee data set with DM1 off (no voltage).

        Args:
            output_path (string): Path to save data set. None will use the default.
            num_exposures (int): Number of exposures.
            coron_exp_time (pint quantity): Exposure time for the coronographics data set.
            direct_exp_time (pint quantity): Exposure time for the direct PSF data set.
            centering (ImageCentering): Image centering algorithm for the coron data set.
            **kwargs: Keyword arguments passed into run_hicat_imaging()
        """
        super(CoffeeDm1OffFocus, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering
        self.kwargs = kwargs

    def experiment(self):

        # # Pure Focus Zernike loop.
        focus_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/dm2_commands/focus/"
        focus_zernike_command_paths = glob(focus_zernike_data_path + "/*p2v/*.fits")

        # DM1 OFF and DM2 focus loop.
        take_coffee_data_set(focus_zernike_command_paths, self.output_path, "focus_dm1_off", self.coron_exp_time,
                             self.direct_exp_time, dm1_command_object=commands.flat_command(bias=False, flat_map=False),
                             num_exposures=self.num_exposures, centering=self.centering, **self.kwargs)
