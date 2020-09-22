import os
import astropy.units as u
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
import numpy as np

from catkit.hardware.iris_ao import segmented_dm_command
from hicat.experiments.modules import pastis_functions
from hicat.experiments.pastis.PastisExperiment import PastisExperiment
from hicat.hardware import testbed_state

from pastis.pastis_analysis import modes_from_file
from pastis.plotting import plot_contrast_per_mode


class PastisModeAmplitudes(PastisExperiment):

    name = 'PASTIS Mode Amplitudes'

    def __init__(self, pastis_results_path, mode_number, c_target, wfe_amplitudes, probe_filename, dm_map_path, color_filter, nd_direct, nd_coron,
                 num_exposures, exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                 align_lyot_stop=True, run_ta=True):
        """
        Pick one mode, scale it by different WFE amplitudes, apply to IrisAO and measure resulting average contrast in DH.

        :param pastis_results_path: str, path to the overall PASTIS data directory, without the 'results' at the end
        :param mode_number: int, mode index of the mode to work on
        :param c_target: float, target contrast for which the mode weights have been calculated
        :param wfe_amplitudes: array of WFE rms in nm to scale the mode by
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
        super().__init__(probe_filename, dm_map_path, color_filter, nd_direct, nd_coron, num_exposures,
                         exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                         align_lyot_stop, run_ta)

        self.mode_number = mode_number
        self.c_target = c_target
        self.wfe_amplitudes = wfe_amplitudes
        self.log.info(f'Will be scaling mode number {mode_number}')
        self.log.info(f'Target contrast: {c_target}')
        self.log.info(f'WFE amplitudes used for scaling: {wfe_amplitudes}')

        # Read PASTIS matrix, modes and mode weights from file
        self.pastis_modes, self.eigenvalues = modes_from_file(pastis_results_path)
        self.mode_weights = np.loadtxt(os.path.join(pastis_results_path, 'results', f'mode_requirements_{c_target}_uniform.txt'))
        self.log.info(f'PASTIS modes and mode weights read from {pastis_results_path}')

        self.measured_contrast = []

    def experiment(self):

        # Run flux normalization
        self.log.info('Starting flux normalization')
        self.run_flux_normalization()

        # Take unaberrated direct and coro images, save normalization factor and coro_floor as attributes
        self.log.info('Measuring reference PSF (direct) and coronagraph floor')
        self.measure_coronagraph_floor()

        # Target contrast needs to be above contrast floor
        if self.c_target <= self.coronagraph_floor:
            raise ValueError(f"Coronagraph floor ({self.coronagraph_floor}) cannot be above target contrast ({self.c_target}).")

        # TODO: save used mode to output folder (txt file or plot of its WFE map, or both)

        # Access testbed devices and set experiment path
        devices = testbed_state.devices.copy()    # TODO: Is this how I will access the IrisDM?
        # iris_dm = devices['iris_dm']
        # Instantiate a connection to the IrisAO
        iris_dm = pastis_functions.IrisAO()

        # Loop over all WFE amplitudes
        for i in range(self.wfe_amplitudes.shape[0]):
            self.log.info(f'Applying scaling of {i}nm rms')
            initial_path = os.path.join(self.output_path, f'wfe_{i}nm')

            # Multiply mode by its mode weight (according to target contrast), and scale by extra WFE amplitude
            opd = self.pastis_modes[:, self.mode_number] * self.mode_weights[self.mode_number] * self.wfe_amplitudes[i]
            opd *= u.nm  # the PASTIS package is currently set up to spit out the modes in units of nm

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
            pair_image, header = self.take_exposure(devices, 'coron', self.wvln, initial_path, dark_zone_mask=self.dark_zone)
            pair_image /= self.direct_max

            # Measure mean contrast
            self.measured_contrast.append(np.mean(pair_image[self.dark_zone]))

        # Save the measured contrasts to file, and the input WFE amplitudes
        np.savetxt(os.path.join(self.output_path, f'scaled_mode_contrasts_{self.c_target}.txt'), self.measured_contrast)
        np.savetxt(os.path.join(self.output_path, f'wfe_amplitudes_{self.c_target}.txt'), self.wfe_amplitudes)

    def post_experiment(self, *args, **kwargs):

        # Plot the results
        fig, ax = plt.subplots(figsize=(11, 8))
        plt.plot(np.array(self.measured_contrast) - self.coronagraph_floor, linewidth=3)  # SUBTRACTING THE BASELINE CONTRAST!!
        plt.title(f'Scaled mode, $c_t = {self.c_target}$', size=29)
        plt.tick_params(axis='both', which='both', length=6, width=2, labelsize=30)
        plt.xlabel('WFE rms (nm)', size=30)
        plt.ylabel('Contrast', size=30)
        plt.gca().yaxis.set_major_formatter(ScalarFormatter(useMathText=True))  # set y-axis formatter to x10^{-10}
        plt.gca().yaxis.offsetText.set_fontsize(30)
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_path, '.'.join([f'scaled_mode_{self.c_target}', 'pdf'])))
