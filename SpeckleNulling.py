from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import os
import numpy as np

from .Experiment import Experiment
from ..hardware.boston.sin_command import sin_command
from ..speckle_nulling import speckle_nulling
from ..hicat_types import units, quantity, FpmPosition, SinSpecification
from ..hardware import testbed
from ..config import CONFIG_INI
from .. import util


class SpeckleNulling(Experiment):
    name = "Speckle Nulling"

    def __init__(self,
                 num_iterations=10,
                 bias=True,
                 flat_map=False,
                 path=None,
                 exposure_time=quantity(1, units.millisecond),
                 num_exposures=2,
                 initial_speckles=SinSpecification(40, 12, quantity(40, units.nanometer), 90)):
        self.num_iterations = num_iterations
        self.bias = bias
        self.flat_map = flat_map
        self.path = path
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.initial_speckles = initial_speckles

    def experiment(self):

        # Wait to set the path until the experiment starts (rather than the constructor)
        if self.path is None:
            self.path = util.create_data_path(suffix="speckle_nulling")

        current_command_object, file_name = sin_command(self.initial_speckles, bias=self.bias, flat_map=self.flat_map,
                                                        return_shortname=True)

        # Initialize the laser and connect to the DM, apply the sine wave shape.
        with testbed.laser_source() as laser:
            coron_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "coron_current")
            laser.set_current(coron_laser_current)
            with testbed.dm_controller() as dm:

                for i in range(0, self.num_iterations):
                    dm.apply_shape(current_command_object, 1)

                    # Tests the dark zone intensity and updates exposure time if needed, otherwise just returns itself.
                    coron_exp_time = speckle_nulling.test_dark_zone_intensity(self.exposure_time, 2)

                    # Take coronographic data, with backgrounds.
                    iteration_path = os.path.join(self.path, "iteration" + str(i))
                    testbed.run_hicat_imaging(coron_exp_time, self.num_exposures, FpmPosition.coron,
                                              path=iteration_path,
                                              exposure_set_name="coron", filename="itr" + str(i) + "_" + file_name)

                    # Run sensing.
                    coron_path = os.path.join(iteration_path, "coron")
                    ncycles_new, angle_deg_new, peak_to_valley_new = speckle_nulling.speckle_sensing(coron_path)

                    # Generate a list of sin_commands at different phases, and take data for each.
                    phase_list = range(0, 360, 30)
                    for phi in phase_list:
                        # Add the current dm command into a new sin_command.
                        new_command, name = sin_command(
                            SinSpecification(angle_deg_new, ncycles_new, peak_to_valley_new, phi),
                            bias=True, return_shortname=True,
                            initial_data=current_command_object.data)
                        dm.apply_shape(new_command, 1)

                        phase_path = os.path.join(iteration_path, "phase" + str(phi))
                        testbed.run_hicat_imaging(coron_exp_time, self.num_exposures, FpmPosition.coron,
                                                  path=phase_path,
                                                  exposure_set_name="coron", filename="itr" + str(i) + "_" + name,
                                                  simulator=False)

                    # Run control on the set of phase shifted data.
                    new_phase = speckle_nulling.speckle_control_phase(iteration_path)

                    # Generate a list of sin_commands a range of amplitudes for the best phase, and take data for each.
                    amplitude_coeff_list = np.arange(0.1, 1.5, 0.2)
                    for ampl_ptv in amplitude_coeff_list:
                        # Add the current dm command into a new sin_command.
                        peak_to_valley_test = peak_to_valley_new * ampl_ptv

                        new_command, name = sin_command(
                            SinSpecification(angle_deg_new, ncycles_new, peak_to_valley_test,
                                             new_phase),
                            bias=True, return_shortname=True,
                            initial_data=current_command_object.data)
                        dm.apply_shape(new_command, 1)

                        amplitude_path = os.path.join(iteration_path, "amplitude" + str(ampl_ptv))
                        testbed.run_hicat_imaging(coron_exp_time, self.num_exposures, FpmPosition.coron,
                                                  path=amplitude_path,
                                                  exposure_set_name="coron", filename="itr" + str(i) + "_" + name,
                                                  simulator=False)

                    # Run control on the set of phase shifted data.
                    new_amplitude_tmp = speckle_nulling.speckle_control_amplitude(iteration_path)
                    new_amplitude = quantity(new_amplitude_tmp, units.nanometer)

                    # Create a new sine wave at the specified phase, and add it to our current_dm_command.
                    phase_correction_command = sin_command(SinSpecification(angle_deg_new, ncycles_new, new_amplitude,
                                                                            new_phase))
                    current_command_object.data += phase_correction_command.data
