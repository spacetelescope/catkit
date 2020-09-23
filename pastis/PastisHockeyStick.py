import os
from astropy.io import fits
import astropy.units as u
import numpy as np

from catkit.hardware.iris_ao import segmented_dm_command
from hicat.experiments.modules import pastis_functions
from hicat.experiments.pastis.PastisExperiment import PastisExperiment
from hicat.hardware import testbed_state

from pastis.config import CONFIG_PASTIS
from pastis.plotting import plot_hockey_stick_curve
import pastis.util


class PastisHockeyStick(PastisExperiment):

    name = 'PASTIS Hockey Stick'

    def __init__(self, rms_range, no_realizations, pastis_matrix_path, probe_filename, dm_map_path, color_filter, nd_direct, nd_coron,
                 num_exposures, exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                 align_lyot_stop=True, run_ta=True):
        super().__init__(probe_filename, dm_map_path, color_filter, nd_direct, nd_coron, num_exposures,
                         exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                         align_lyot_stop, run_ta)

        self.rms_range = rms_range
        self.no_realizations = no_realizations
        self.log.info(f'Number of rms values tested: {rms_range.shape[0]}')
        self.log.info(f'Number of realizations per rms value: {no_realizations}')

        # Read PASTIS matrix from file
        try:
            self.pastis_matrix = fits.getdata(os.path.join(pastis_matrix_path))
            self.log.info(f'PASTIS matrix read from {pastis_matrix_path}')
        except FileNotFoundError:
            self.log.warning('PASTIS matrix not found. Will only perform empirical measurements.')
            self.pastis_matrix = None

        self.measured_contrast = np.zeros((self.rms_range.shape[0], self.no_realizations))
        self.pastis_contrast = np.copy(self.measured_contrast)

        self.measured_mean_over_realizations = []
        self.pastis_mean_over_realizations = []

    def experiment(self):

        # Run flux normalization
        self.log.info('Starting flux normalization')
        self.run_flux_normalization()

        # Take unaberrated direct and coro images, save normalization factor and coro_floor as attributes
        self.log.info('Measuring reference PSF (direct) and coronagraph floor')
        self.measure_coronagraph_floor()

        # Access testbed devices and set experiment path
        devices = testbed_state.devices.copy()    # TODO: Is this how I will access the IrisDM?
        # iris_dm = devices['iris_dm']
        # Instantiate a connection to the IrisAO
        iris_dm = pastis_functions.IrisAO()

        # Loop over all WFE amplitudes
        for i, rms in enumerate(self.rms_range):
            initial_path = os.path.join(self.output_path, f'rms_{rms}nm')
            rms *= u.nm  # Making sure this has the correct units

            for j in range(self.no_realizations):

                self.log.info(f"CALCULATING CONTRAST FOR {rms}nm rms")
                self.log.info(f"WFE RMS number {i + 1}/{self.rms_range.shape[0]}")
                self.log.info(f"Random realization: {j + 1}/{self.no_realizations}")
                self.log.info(f"Total: {(i * self.no_realizations) + (j + 1)}/{self.rms_range.shape[0] * self.no_realizations}")

                # Create random aberration coefficients on segments, scaled to total rms
                aber = pastis.util.create_random_rms_values(self.nb_seg, rms)    # comes back in u.nm

                # Convert this to IrisAO command - a list of 37 tuples of 3 (PTT)
                # TODO: make it such that we can pick between piston, tip and tilt (will require extra keyword "zernike")
                command_list = []
                for seg in range(self.nb_seg):
                    command_list.append((aber[seg], 0, 0))
                #aber_command = segmented_dm_command.load_command(command_list, apply_flat_map=True, dm_config_id='iris_ao')
                aber_command = None

                # Apply this to IrisAO
                iris_dm.apply_shape(aber_command)

                # Take coro images
                pair_image, header = self.take_exposure(devices, 'coron', self.wvln, initial_path,
                                                        dark_zone_mask=self.dark_zone, suffix=f'realization_{j}')
                pair_image /= self.direct_max

                # Measure mean contrast
                self.measured_contrast[i, j] = np.mean(pair_image[self.dark_zone])

                # Calculate contrast from the very same aberration but through PASTIS propagation
                if self.pastis_matrix is not None:
                    self.pastis_contrast[i, j] = pastis.util.pastis_contrast(aber, self.pastis_matrix) + self.coronagraph_floor

        # Calculate the mean contrast across realizations
        self.measured_mean_over_realizations.append(np.mean(self.measured_contrast, axis=1))
        self.pastis_mean_over_realizations.append(np.mean(self.pastis_contrast, axis=1))

        # Save the measured and calculated contrasts to file, and the input WFE amplitudes
        np.savetxt(os.path.join(self.output_path, 'hockey_measured_contrasts.txt'), self.measured_contrast)
        np.savetxt(os.path.join(self.output_path, 'hockey_pastis_contrasts.txt'), self.pastis_contrast)
        np.savetxt(os.path.join(self.output_path, 'hockey_measured_contrasts_avg_over_realizations.txt'), self.measured_mean_over_realizations)
        np.savetxt(os.path.join(self.output_path, 'hockey_pastis_contrasts_avg_over_realizations.txt'), self.pastis_mean_over_realizations)
        np.savetxt(os.path.join(self.output_path, 'hockey_rms_range.txt'), self.rms_range)

    def post_experiment(self, *args, **kwargs):

        # Plot the results
        plot_hockey_stick_curve(self.rms_range, self.pastis_mean_over_realizations[0],
                                self.measured_mean_over_realizations[0], wvln=CONFIG_PASTIS.getfloat('HiCAT', 'lambda'),
                                out_dir=self.output_path, fname_suffix=f'{self.no_realizations}_realizations_each',
                                save=True)
