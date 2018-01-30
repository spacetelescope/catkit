from __future__ import (absolute_import, division,
                        unicode_literals)

import os
import logging

# noinspection PyUnresolvedReferences
from builtins import *

from hicat.hicat_types import ImageCentering
from .modules import double_sine
from .Experiment import Experiment
from .. import util
from ..config import CONFIG_INI
from ..hardware import testbed
from ..hardware.boston.sin_command import sin_command
from ..hicat_types import units, quantity, FpmPosition, SinSpecification, LyotStopPosition


class DoubleSinRemoveCrossterm(Experiment):
    name = "Double Sin Remove Crossterm"

    def __init__(self,
                 path=None,
                 bias=False,
                 flat_map=True,
                 coron_exposure_time=quantity(200, units.millisecond),
                 direct_exposure_time=quantity(250, units.microsecond),
                 coron_nexps=10,
                 direct_nexps=10,
                 angle=0,
                 ncycles_range=range(6, 18, 1),
                 peak_to_valley_range=range(5, 55, 5),
                 phase=0,
                 fpm_position=FpmPosition.coron,
                 lyot_stop_position=LyotStopPosition.in_beam,
                 alignment_speckle=False,
                 centering=ImageCentering.auto,
                 auto_exposure_mask_size=5.5,
                 **kwargs):
        self.path = path
        self.bias = bias
        self.flat_map = flat_map
        self.coron_exposure_time = coron_exposure_time
        self.direct_exposure_time = direct_exposure_time
        self.coron_nexps = coron_nexps
        self.direct_nexps = direct_nexps
        self.angle = angle
        self.ncycles_range = ncycles_range
        self.peak_to_valley_range = peak_to_valley_range
        self.phase = phase
        self.fpm_position = fpm_position
        self.lyot_stop_position = lyot_stop_position
        self.alignment_speckle = alignment_speckle
        self.auto_exposure_mask_size = auto_exposure_mask_size
        self.centering = centering
        self.kwargs = kwargs

    def experiment(self):

        """
        Take three sets of data using the take_double_sin_exposures function: Coron, Direct, Saturated Direct. Then also
        take a flat data set with no sinewave applied (just a bias).
        """

        if self.alignment_speckle:
            self.centering = ImageCentering.injected_speckles

        # Wait to set the path until the experiment starts (rather than the constructor)
        if self.path is None:
            self.path = util.create_data_path(suffix="double_sin")
            util.setup_hicat_logging(self.path, "double_sin")

        coron_dirname = "coron"
        direct_dirname = "direct"

        with testbed.laser_source() as laser:
            for ncycle in self.ncycles_range:
                ncycles_path = os.path.join(self.path, "ncycles" + str(ncycle))
                for p2v in self.peak_to_valley_range:
                    peak_to_valley_quantity = quantity(p2v, units.nanometer)
                    sin_spec = SinSpecification(self.angle, ncycle, peak_to_valley_quantity, self.phase)
                    p2v_path = os.path.join(ncycles_path, "p2v_" + str(p2v) + "nm")

                    # Coron.
                    coron_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "coron_current")
                    laser.set_current(coron_laser_current)
                    double_sine.double_sin_remove_crossterm(sin_spec, self.alignment_speckle, self.bias, self.flat_map,
                                                            self.coron_exposure_time,
                                                            self.coron_nexps, FpmPosition.coron,
                                                            self.auto_exposure_mask_size,
                                                            path=os.path.join(p2v_path, coron_dirname),
                                                            centering=self.centering,
                                                            **self.kwargs)

                    # Direct.
                    direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
                    laser.set_current(direct_laser_current)
                    sin_command_object, sin_file_name = sin_command(sin_spec, bias=self.bias, flat_map=self.flat_map,
                                                                    return_shortname=True)
                    with testbed.dm_controller() as dm:

                        # Postive sin wave.
                        dm.apply_shape(sin_command_object, 1)
                        testbed.run_hicat_imaging(self.direct_exposure_time, self.direct_nexps,
                                                  FpmPosition.direct,
                                                  path=p2v_path, exposure_set_name=direct_dirname,
                                                  filename=sin_file_name, centering=ImageCentering.psf,
                                                  auto_exposure_mask_size=None,
                                                  **self.kwargs)
