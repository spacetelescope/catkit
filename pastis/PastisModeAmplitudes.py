import os
import astropy.units as u
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
        super().__init__(probe_filename, dm_map_path, color_filter, nd_direct, nd_coron, num_exposures,
                         exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                         align_lyot_stop, run_ta)

        self.mode_number = mode_number
        self.c_target = c_target
        self.wfe_amplitudes = wfe_amplitudes

        # Read PASTIS matrix, modes and mode weights from file
        self.pastis_modes, self.eigenvalues = modes_from_file(pastis_results_path)
        self.mode_weights = np.loadtxt(os.path.join(pastis_results_path, 'results', f'mode_requirements_{c_target}_uniform.txt'))

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
            initial_path = os.path.join(self.output_path, f'wfe_{i}nm')

            # Multiply mode by its mode weighth (according to target contrast), and scale by extra WFE amplitude
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
        plot_contrast_per_mode(self.measured_contrast, self.coronagraph_floor, self.c_target,
                               nmodes=len(self.measured_contrast), out_dir=self.output_path, save=True)
