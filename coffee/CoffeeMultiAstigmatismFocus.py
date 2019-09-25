from glob import glob
import logging

from hicat.experiments.Experiment import Experiment
from hicat import util
from hicat.hicat_types import units, quantity, ImageCentering
from hicat.experiments.modules.general import take_coffee_data_set


class CoffeeMultiAstigmatismFocus(Experiment):
    """
    Uses a set of high quality commands created in front of the 4d that combined astigmatism and focus into
    a single DM command.

    Args:
        path (string): Path to save data set. None will use the default.
        num_exposures (int): Number of exposures.
        coron_exp_time (pint quantity): Exposure time for the coronographics data set.
        direct_exp_time (pint quantity): Exposure time for the direct PSF data set.
        centering (ImageCentering): Image centering algorithm for the coron data set.
        **kwargs: Keyword arguments passed into run_hicat_imaging()
    """

    name = "Coffee Multi Astigmatism Focus"
    log = logging.getLogger(__name__)

    def __init__(self,
                 output_path=None,
                 num_exposures=10,
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(1, units.millisecond),
                 centering=ImageCentering.custom_apodizer_spots,
                 suffix = "coffee_multi_astigmatism_focus",
                 **kwargs):

        super(CoffeeMultiAstigmatismFocus, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering
        self.kwargs = kwargs

    def experiment(self):

        # Multi astigmatsm+focus loop.
        multi_zernike_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/dm2_commands/astigmastism_80nm"
        multi_zernike_command_paths = glob(multi_zernike_data_path + "/*/*.fits")

        take_coffee_data_set(multi_zernike_command_paths, self.output_path,
                             "astigmatism_80nm", self.coron_exp_time,
                             self.direct_exp_time, num_exposures=self.num_exposures,
                             centering=self.centering, **self.kwargs)
