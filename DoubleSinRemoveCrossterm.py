from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from .Experiment import Experiment
from .double_sine import *


class DoubleSinRemoveCrossterm(Experiment):
    def __init__(self,
                 path=CONFIG_INI.get("optics_lab", "local_data_path"),
                 bias=True,
                 flat_map=False,
                 coron_exposure_time=quantity(20, units.millisecond),
                 direct_exposure_time=quantity(250, units.microsecond),
                 coron_nexps=10,
                 direct_nexps=10,
                 angle=0,
                 ncycles_range=range(6, 18, 1),
                 peak_to_valley_range=range(5, 55, 5),
                 phase=0):
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

    def experiment(self):

        """
        Take three sets of data using the take_double_sin_exposures function: Coron, Direct, Saturated Direct. Then also
        take a flat data set with no sinewave applied (just a bias).
        """

        # Create the date-time string to use as the experiment path.
        base_path = util.create_data_path(initial_path=self.path, suffix="double_sin")
        coron_dirname = "coron"
        direct_dirname = "direct"

        with laser_source() as laser:
            for ncycle in self.ncycles_range:
                ncycles_path = os.path.join(base_path, "ncycles" + str(ncycle))
                for p2v in self.peak_to_valley_range:
                    peak_to_valley_quantity = quantity(p2v, units.nanometer)
                    sin_spec = SinSpecification(self.angle, ncycle, peak_to_valley_quantity, self.phase)
                    p2v_path = os.path.join(ncycles_path, "p2v_" + str(p2v) + "nm")

                    # Coron.
                    coron_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "coron_current")
                    laser.set_current(coron_laser_current)
                    double_sin_remove_crossterm(sin_spec, self.bias, self.flat_map, self.coron_exposure_time,
                                                self.coron_nexps, FpmPosition.coron,
                                                path=os.path.join(p2v_path, coron_dirname))

                    # Direct.
                    direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
                    laser.set_current(direct_laser_current)
                    sin_command_object, sin_file_name = sin_command(sin_spec, bias=self.bias, flat_map=self.flat_map,
                                                                    return_shortname=True)
                    with dm_controller() as dm:
                        # Postive sin wave.
                        dm.apply_shape(sin_command_object, 1)
                        run_hicat_imaging(self.direct_exposure_time, self.direct_nexps, FpmPosition.direct,
                                          path=p2v_path, exposure_set_name=direct_dirname, filename=sin_file_name)
