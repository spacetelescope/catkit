import os
import astropy.units as u
import numpy as np

from catkit.hardware.iris_ao import segmented_dm_command
from hicat.experiments.modules import pastis_functions
from hicat.experiments.pastis.PastisExperiment import PastisExperiment
from hicat.hardware import testbed_state

from pastis.pastis_analysis import modes_from_file
from pastis.plotting import plot_monte_carlo_simulation


class PastisMonteCarlo(PastisExperiment):

    def __init__(self, segments, pastis_results_path, n_repeat, c_target, probe_filename, dm_map_path, color_filter,
                 nd_direct, nd_coron, num_exposures, exposure_time_coron, exposure_time_direct, auto_expose, file_mode,
                 raw_skip, align_lyot_stop=True, run_ta=True):
        """
        Run a Monte Carlo analysis on the average contrast in DH, either from random PASTIS mode weights or segment weights.

        :param segments: bool, if True, will draw random segment weights, if False, will draw random mode weights
        :param pastis_results_path: str, path to the overall PASTIS data directory, without the 'results' at the end
        :param n_repeat: int, number of random realizations of WFE to be drawn
        :param c_target: float, target contrast for which the mode weights have been calculated
        :param probe_filename: str, path to probe file, used only to get DH geometry
        :param dm_map_path: str, path to folder that contains DH solution
        :param color_filter: str, wavelength for color flipmount
        :param nd_direct: str, ND filter choice for direct images
        :param nd_coron: str, ND filter choice for coronagraphic images
        :param num_exposures: int, number of exposures for each image acquisition
        :param exposure_time_coron: float, exposure time for coron mode in microseconds
        :param exposure_time_direct: float, exposure time for direct mode in microseconds
        :param auto_expose: bool or {catkit.catkit_types.FpmPosition: bool}, flag to enable auto exposure time correction
        :param file_mode: bool, If true files will be written to disk otherwise only final results are saved
        :param raw_skip: int, Skips x writing-files for every one taken. raw_skip=math.inf will skip all and save no raw image files.
        :param align_lyot_stop: bool, whether to automatically align the Lyot stop before the experiment or not
        :param run_ta: bool, whether to run target acquisition. Will still just measure TA if False.
        """

        if segments:
            self.name = 'PASTIS Monte Carlo Segments'
        else:
            self.name = 'PASTIS Monte Carlo Modes'

        super().__init__(probe_filename, dm_map_path, color_filter, nd_direct, nd_coron, num_exposures,
                         exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                         align_lyot_stop, run_ta)

        self.segments = segments
        self.n_repeat = n_repeat
        self.c_target = c_target

        # Read PASTIS matrix, modes and mode/segment weights from file
        self.pastis_results_path = pastis_results_path
        if self.segments:
            self.segment_weights = np.loadtxt(os.path.join(self.pastis_results_path, 'results', f'segment_requirements_{self.c_target}.txt'))
            self.segment_weights *= u.nm
        else:
            self.pastis_modes, self.eigenvalues = modes_from_file(self.pastis_results_path)
            self.mode_weights = np.loadtxt(os.path.join(self.pastis_results_path, 'results', f'mode_requirements_{self.c_target}_uniform.txt'))

        self.measured_contrast = []
        self.random_weights = []

    def experiment(self):

        # A couple of initial log messages
        if self.segments:
            self.log.info('Working on MC for SEGMENTS.')
            self.log.info(f'Segment weights read from {self.pastis_results_path}')
        else:
            self.log.info('Working on MC for MODES.')
            self.log.info(f'PASTIS modes and mode weights read from {self.pastis_results_path}')
        self.log.info(f'Target contrast: {self.c_target}')
        self.log.info(f'Will run {self.n_repeat} iterations.')

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

        # Loop over all modes/segments
        for rep in range(self.n_repeat):

            # Define a numpy random state
            mc_random_state = np.random.RandomState()

            if self.segments:
                self.log.info(f'Random segment set realization {rep + 1}/{self.n_repeat}')

                # Draw a normal distribution for each segment, where the stddevs are the segment weights
                random_opd = mc_random_state.normal(0, self.segment_weights) * u.nm
                self.random_weights.append(random_opd)

            else:
                self.log.info(f'Random mode set realization {rep + 1}/{self.n_repeat}')

                # Draw a normal distribution for each mode, where the stddevs are the mode weights
                random_weights = mc_random_state.normal(0, self.mode_weights)
                self.random_weights.append(random_weights)

                # Sum up all modes with randomly scaled weights to make total random OPD
                random_opd = np.nansum(self.pastis_modes * random_weights, axis=1)
                random_opd *= u.nm

            # Convert this to IrisAO command - a list of 37 tuples of 3 (PTT)
            # TODO: make it such that we can pick between piston, tip and tilt (will require extra keyword "zernike")
            command_list = []
            for seg in range(self.nb_seg):
                command_list.append((random_opd[seg], 0, 0))
            #random_opd_command = segmented_dm_command.load_command(command_list, apply_flat_map=True, dm_config_id='iris_ao')
            random_opd_command = None

            # Apply this to IrisAO
            iris_dm.apply_shape(random_opd_command)

            # TODO: save random OPD command on IrisAO as WFE map

            # Take coro images
            pair_image, header = self.take_exposure(devices, 'coron', self.wvln, initial_path,
                                                    suffix=f'realization_{rep}', dark_zone_mask=self.dark_zone)
            pair_image /= self.direct_max

            # Measure mean contrast
            self.measured_contrast.append(np.mean(pair_image[self.dark_zone]))

        # Save the measured contrasts and random weights to file
        if self.segments:
            filename_contrasts = f'mc_segments_contrasts_{self.c_target}.txt'
            filename_weights = f'mc_segment_req_maps_{self.c_target}.txt'
        else:
            filename_contrasts = f'mc_modes_contrasts_{self.c_target}.txt'
            filename_weights = f'mc_mode_reqs_{self.c_target}.txt'
        np.savetxt(os.path.join(self.output_path, filename_contrasts), self.measured_contrast)
        np.savetxt(os.path.join(self.output_path, filename_weights), self.random_weights)

    def post_experiment(self, *args, **kwargs):

        # Calculate the empirical mean and standard deviation of the distribution
        mean_empirical = np.mean(self.measured_contrast)
        stddev_empirical = np.std(self.measured_contrast)
        self.log.info(f'Mean of the Monte Carlo result: {mean_empirical}')
        self.log.info(f'Standard deviation of the Monte Carlo result: {stddev_empirical}')
        with open(os.path.join(self.output_path, f'statistical_contrast_empirical_{self.c_target}.txt'), 'w') as file:
            file.write(f'Empirical, statistical mean: {mean_empirical}')
            file.write(f'\nEmpirical variance: {stddev_empirical**2}')

        # Plot histogram
        plot_monte_carlo_simulation(np.array(self.measured_contrast), out_dir=self.output_path, c_target=self.c_target,
                                    segments=self.segments, stddev=stddev_empirical, save=True)
