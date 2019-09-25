import logging
import os
import numpy as np
from glob import glob
from astropy.io import fits

from hicat.experiments.Experiment import Experiment
from hicat.hardware.boston.sin_command import sin_command
from hicat.hardware.boston.commands import flat_command

from hicat.speckle_nulling import speckle_nulling
from hicat.hicat_types import units, quantity, FpmPosition, SinSpecification, LyotStopPosition, ImageCentering
from hicat.hardware import testbed
from hicat.hardware.boston import DmCommand
from hicat.config import CONFIG_INI
from hicat.hardware import testbed_state
from hicat import util


class SpeckleNulling(Experiment):
    name = "Speckle Nulling"
    log = logging.getLogger(__name__)

    def __init__(self,
                 num_iterations=10,
                 bias=False,
                 flat_map=True,
                 output_path=None,
                 exposure_time=quantity(100, units.millisecond),
                 num_exposures=3,
                 dm_command_path=None,
                 initial_speckles=SinSpecification(10, 12, quantity(25, units.nanometer), 90),
                 suffix="speckle_nulling",
                 fpm_position=FpmPosition.coron,
                 lyot_stop_position=LyotStopPosition.in_beam,
                 centering=ImageCentering.global_cross_correlation,
                 reference_centering=ImageCentering.custom_apodizer_spots,
                 **kwargs):
        super(SpeckleNulling, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.num_iterations = num_iterations
        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.dm_command_path = dm_command_path
        self.initial_speckles = initial_speckles
        self.fpm_position = fpm_position
        self.lyot_stop_position = lyot_stop_position
        self.centering = centering
        self.reference_centering = reference_centering
        self.kwargs = kwargs

    def experiment(self):

        # Start with a previously stored DM command if dm_command_path is passed in.
        if self.dm_command_path:
            current_command_object = DmCommand.load_dm_command(self.dm_command_path,
                                                               bias=self.bias,
                                                               flat_map=self.flat_map)
            file_name = "flat_map" if self.flat_map else "bias"
            if self.initial_speckles:
                self.log.info("Ignoring initial speckles and loading dm_command from disk.")

        # Inject sin waves if initial_speckles is passed in.
        elif self.initial_speckles:
            current_command_object, file_name = sin_command(self.initial_speckles, bias=self.bias,
                                                            flat_map=self.flat_map,
                                                            return_shortname=True)

        # Create a flat map or bias command if no dm_command_path or initial_speckles are passed in.
        else:
            current_command_object, file_name = flat_command(bias=self.bias,
                                                             flat_map=self.flat_map,
                                                             return_shortname=True)

        # Set the starting exposure time.
        auto_exposure_time = self.exposure_time

        # Set the exposure set name and laser current based on FPM position.
        if self.fpm_position.value == FpmPosition.coron.value:
            exp_set_name = "coron"
            laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "coron_current")
        else:
            exp_set_name = "direct"
            laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")

        # Initialize the laser and connect to the DM, apply the sine wave shape.
        with testbed.laser_source() as laser:
            laser.set_current(laser_current)

            with testbed.dm_controller() as dm:

                # Apply a flat map to DM2.
                dm.apply_shape(flat_command(flat_map=True, dm_num=2), 2)

                for i in range(0, self.num_iterations):
                    dm.apply_shape(current_command_object, 1)

                    # Global alignment reference centering (optional).
                    centering = self.centering
                    if i == 0 and self.centering.value == ImageCentering.global_cross_correlation.value:
                        centering = self.reference_centering
                        testbed_state.global_alignment_mask = self.__make_global_alignment_mask()
                        auto_exposure_time = testbed.auto_exp_time_no_shape(auto_exposure_time,
                                                                            40000,
                                                                            50000,
                                                                            mask=np.invert(testbed_state.global_alignment_mask),
                                                                            centering=centering,
                                                                            pipeline=True)

                        # Take coronographic data, with backgrounds.
                        ref_path = os.path.join(self.output_path, "reference")
                        testbed.run_hicat_imaging(auto_exposure_time, self.num_exposures, self.fpm_position,
                                                  lyot_stop_position=self.lyot_stop_position,
                                                  centering=centering,
                                                  path=ref_path, auto_exposure_time=False,
                                                  exposure_set_name=exp_set_name,
                                                  filename="itr" + str(i) + "_" + file_name,
                                                  **self.kwargs)
                        image_path = glob(os.path.join(ref_path, "coron", "*_cal.fits"))[0]
                        testbed_state.reference_image = fits.getdata(image_path)

                    # Tests the dark zone intensity and updates exposure time if needed, or just returns itself.
                    auto_exposure_time = speckle_nulling.test_dark_zone_intensity(
                        auto_exposure_time, 2,
                        fpm_position=self.fpm_position,
                        lyot_stop_position=self.lyot_stop_position,
                        centering=centering)

                    # Take coronographic data, with backgrounds.
                    iteration_path = os.path.join(self.output_path, "iteration" + str(i))
                    testbed.run_hicat_imaging(auto_exposure_time, self.num_exposures, self.fpm_position,
                                              lyot_stop_position=self.lyot_stop_position,
                                              centering=self.centering,
                                              path=iteration_path, auto_exposure_time=False,
                                              exposure_set_name=exp_set_name, filename="itr" + str(i) + "_" + file_name,
                                              **self.kwargs)

                    # Run sensing.
                    coron_path = os.path.join(iteration_path, exp_set_name)
                    ncycles_new, angle_deg_new, peak_to_valley_new = speckle_nulling.speckle_sensing(coron_path)

                    # Generate a list of sin_commands at different phases, and take data for each.
                    phase_list = range(0, 360, 45)
                    for phi in phase_list:
                        # Add the current dm command into a new sin_command.
                        new_command, name = sin_command(
                            SinSpecification(angle_deg_new, ncycles_new, peak_to_valley_new, phi),
                            bias=self.bias, flat_map=self.flat_map, return_shortname=True,
                            initial_data=current_command_object.data)
                        dm.apply_shape(new_command, 1)

                        phase_path = os.path.join(iteration_path, "phase" + str(phi))

                        testbed.run_hicat_imaging(auto_exposure_time, self.num_exposures, self.fpm_position,
                                                  lyot_stop_position=self.lyot_stop_position,
                                                  path=phase_path, auto_exposure_time=False,
                                                  centering=self.centering,
                                                  exposure_set_name=exp_set_name, filename="itr" + str(i) + "_" + name,
                                                  simulator=False, **self.kwargs)

                    # Run control on the set of phase shifted data.
                    new_phase = speckle_nulling.speckle_control_phase(iteration_path, exp_set_name)

                    # Generate a list of sin_commands a range of amplitudes for the best phase, and take data for each.
                    amplitude_coeff_list = np.arange(0.2, 2.0, 0.4)
                    for ampl_ptv in amplitude_coeff_list:
                        # Add the current dm command into a new sin_command.
                        peak_to_valley_test = peak_to_valley_new * ampl_ptv

                        new_command, name = sin_command(
                            SinSpecification(angle_deg_new, ncycles_new, peak_to_valley_test,
                                             new_phase),
                            bias=self.bias, flat_map=self.flat_map, return_shortname=True,
                            initial_data=current_command_object.data)
                        dm.apply_shape(new_command, 1)

                        amplitude_path = os.path.join(iteration_path, "amplitude" + str(ampl_ptv))

                        testbed.run_hicat_imaging(auto_exposure_time, self.num_exposures, self.fpm_position,
                                                  lyot_stop_position=self.lyot_stop_position,
                                                  centering=self.centering,
                                                  path=amplitude_path, auto_exposure_time=False,
                                                  exposure_set_name=exp_set_name, filename="itr" + str(i) + "_" + name,
                                                  simulator=False, **self.kwargs)

                    # Run control on the set of phase shifted data.
                    new_amplitude_tmp = speckle_nulling.speckle_control_amplitude(iteration_path, exp_set_name)
                    new_amplitude = quantity(new_amplitude_tmp, units.nanometer)

                    # Create a new sine wave at the specified phase, and add it to our current_dm_command.
                    phase_correction_command = sin_command(SinSpecification(angle_deg_new, ncycles_new, new_amplitude,
                                                                            new_phase))
                    current_command_object.data += phase_correction_command.data

                # Take a final (non-saturated) image using auto exposure without the dark zone mask.
                testbed.run_hicat_imaging(self.exposure_time, self.num_exposures, self.fpm_position,
                                          centering=self.centering,
                                          lyot_stop_position=self.lyot_stop_position,
                                          path=self.output_path,
                                          exposure_set_name="final", filename="final_dark_zone.fits",
                                          simulator=False, **self.kwargs)


    @staticmethod
    def __make_global_alignment_mask():
        radius = CONFIG_INI.getint("speckle_nulling", "global_alignment_mask_radius")
        camera = CONFIG_INI.get("testbed", "imaging_camera")
        width = CONFIG_INI.getint(camera, "width")
        height = CONFIG_INI.getint(camera, "height")
        center_x = int(round(width / 2))
        center_y = int(round(height / 2))

        # Make a mask as big as the CNT apodizer's natural dark zone.
        return util.circular_mask((center_x, center_y), radius, (width, height))
