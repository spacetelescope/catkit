import os
import astropy.units as u
import numpy as np

from catkit.hardware.iris_ao import segmented_dm_command
from hicat.experiments.modules import pastis_functions
from hicat.experiments.pastis.PastisExperiment import PastisExperiment
from hicat.hardware import testbed_state

from pastis.pastis_analysis import modes_from_file
from pastis.plotting import plot_monte_carlo_simulation


class PastisMonteCarloModes(PastisExperiment):

    name = "PASTIS Monte Carlo Modes"

    def __init__(self, pastis_results_path, n_repeat, c_target, probe_filename, dm_map_path, color_filter, nd_direct, nd_coron,
                 num_exposures, exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                 align_lyot_stop=True, run_ta=True):

        super().__init__(probe_filename, dm_map_path, color_filter, nd_direct, nd_coron, num_exposures,
                         exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                         align_lyot_stop, run_ta)

        self.n_repeat = n_repeat
        self.c_target = c_target
        self.log.info(f'Target contrast: {c_target}')
        self.log.info(f'Will run {n_repeat} iterations.')

        # Read PASTIS matrix, modes and mode weights from file
        self.pastis_modes, self.eigenvalues = modes_from_file(pastis_results_path)
        self.mode_weights = np.loadtxt(os.path.join(pastis_results_path, 'results', f'mode_requirements_{c_target}_uniform.txt'))
        self.log.info(f'PASTIS modes and mode weights read from {pastis_results_path}')

        self.measured_contrast = []
        self.random_mode_weight_sets = []

    def experiment(self):

        # Access devices for reference images
        devices = testbed_state.devices.copy()

        # Run flux normalization
        self.log.info('Starting flux normalization')
        self.run_flux_normalization(devices)

        # Take unaberrated direct and coro images, save normalization factor and coro_floor as attributes
        self.log.info('Measuring reference PSF (direct) and coronagraph floor')
        self.measure_coronagraph_floor(devices)

        # Target contrast needs to be above contrast floor
        if self.c_target <= self.coronagraph_floor:
            raise ValueError(f"Coronagraph floor ({self.coronagraph_floor}) cannot be above target contrast ({self.c_target}).")

        initial_path = os.path.join(self.output_path, 'all_random_realizations')

        # iris_dm = devices['iris_dm']    # TODO: Is this how I will access the IrisDM?
        # Instantiate a connection to the IrisAO
        iris_dm = pastis_functions.IrisAO()

        # Loop over all modes
        for rep in range(self.n_repeat):
            self.log.info(f'Random mode set realization {rep + 1}/{self.n_repeat}')

            # Create a random set of mode weights
            modes_random_state = np.random.RandomState()
            rand = modes_random_state.normal(0, 1, self.nb_seg)
            random_weights = self.mode_weights * rand
            self.random_mode_weight_sets.append(random_weights)

            # Sum up all modes with randomly scaled sigmas to make total OPD
            opd = np.nansum(self.pastis_modes[:, :] * random_weights, axis=1)
            opd *= u.nm

            # Convert this to IrisAO command - a list of 37 tuples of 3 (PTT)
            # TODO: make it such that we can pick between piston, tip and tilt (will require extra keyword "zernike")
            command_list = []
            for seg in range(self.nb_seg):
                command_list.append((opd[seg], 0, 0))
            #opd_command = segmented_dm_command.load_command(command_list, apply_flat_map=True, dm_config_id='iris_ao')
            opd_command = None

            # Apply this to IrisAO
            iris_dm.apply_shape(opd_command)

            # Take coro images
            pair_image, header = self.take_exposure(devices, 'coron', self.wvln, initial_path,
                                                    suffix=f'realization_{rep}', dark_zone_mask=self.dark_zone)
            pair_image /= self.direct_max

            # Measure mean contrast
            self.measured_contrast.append(np.mean(pair_image[self.dark_zone]))

        # Save the measured contrasts and random mode sets to file
        np.savetxt(os.path.join(self.output_path, f'mc_modes_contrasts_{self.c_target}.txt'), self.measured_contrast)
        np.savetxt(os.path.join(self.output_path, f'mc_mode_reqs_{self.c_target}.txt'), self.random_mode_weight_sets)

    def post_experiment(self, *args, **kwargs):

        # Calculate the empirical mean and standard deviation of the distribution
        mean_modes = np.mean(self.measured_contrast)
        stddev_modes = np.std(self.measured_contrast)
        self.log.info(f'Mean of the Monte Carlo result modes: {mean_modes}')
        self.log.info(f'Standard deviation of the Monte Carlo result modes: {stddev_modes}')
        with open(os.path.join(self.output_path, f'statistical_contrast_empirical_{self.c_target}.txt'), 'w') as file:
            file.write(f'Empirical, statistical mean: {mean_modes}')
            file.write(f'\nEmpirical variance: {stddev_modes**2}')

        # Plot histogram
        plot_monte_carlo_simulation(self.measured_contrast, out_dir=self.output_path, c_target=self.c_target,
                                    segments=False, stddev=stddev_modes, save=True)
