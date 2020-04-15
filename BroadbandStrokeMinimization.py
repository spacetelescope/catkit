# flake8: noqa: E402
import hicat.simulators
sim = hicat.simulators.auto_enable_sim()

from hicat.config import CONFIG_INI

import numpy as np
import os
import glob
from astropy.io import fits
import hcipy

from hicat.control.target_acq import TargetAcquisition
from hicat.hardware import testbed
import hicat.plotting.animation
from hicat import util
from hicat.wfc_algorithms import stroke_min
from hicat.experiments.StrokeMinimization import StrokeMinimization

from hicat.hardware.testbed import move_filter


class BroadbandStrokeMinimization(StrokeMinimization):
    """ Broadband implementation of stroke minimization.


    The wavelengths to use are automatically inferred from the provided Jacobians.

    :param jacobian_filenames: List of Jacobian matrix file name paths
    :param probe_filenames: List of Observation matrix file name paths (must be same length as jacobian_filenames)
    :param num_iterations:  Number of iterations to run before convergence
    :param num_exposures:  Number of exposures for the camera
    :param exposure_time_coron:  Exposure time in the coronagraphic mode (microsec)
    :param exposure_time_direct:  Exposure time in the direct mode (microsec)
    :param use_dm2: Bool to use DM2 for control (2 sided DZ) or not (1 sided)
    :param autoscale_e_field:  [Hack Mode] Brute force autoscaling of the E-field to match intensity at each iteration
    :param direct_every:  defines how often a direct image is taken for the contrast calibration
    :param resume: bool, try to find and reuse DM settings from prior dark zone.
    :param dm_command_dir_to_restore: string, path to the directory where the dm_commands are located for restoring dm
           settings.
    :param dm_calibration_fudge: coefficient on DM2 for rescaling. probably temporary.
    :param mu_step_factor:  Multiplicative factor by which to change the regularization parameter when finding optimal DM update
    :param control_weights: How much to weight each wavelength in the control problem
    :param spectral_weights: Relative intensity of source at each wavelength
    :param perfect_knowledge_mode: Whether to use perfect-knowledge of the electric field as input to the controller, instead of the pairwise-probe estimate.  Only works in simulation.
    :param file_mode: If true files will be written to disk otherwise only final plots are saved.
    :param raw_skip: Skips x writes for every one taken. raw_skip=math.inf will skip all and save no raw image files.
    """
    def __init__(self, wavelengths, jacobian_filenames, probe_filenames, num_iterations,
                 num_exposures=10,
                 exposure_time_coron=100000,
                 exposure_time_direct=100,
                 use_dm2=False,
                 gamma=0.8,
                 auto_adjust_gamma=False,
                 control_gain=1.0,
                 autoscale_e_field=False,
                 direct_every=1,
                 resume=False,
                 dm_command_dir_to_restore=None,
                 dm_calibration_fudge=1,
                 mu_start=1e-7,
                 suffix='broadband_stroke_minimization',
                 nd_direct=None,
                 nd_coron=None,
                 control_weights=None,
                 spectral_weights=None,
                 perfect_knowledge_mode=False,
                 file_mode=True,
                 raw_skip=0):
        super(StrokeMinimization, self).__init__(suffix=suffix)

        # TODOs:
        # - Don't correct for ND filter flux in monochromatic mode
        # - Don't take data for wavelengths that have 0 weight

        self.file_mode = file_mode
        self.raw_skip = raw_skip

        if CONFIG_INI['testbed']['laser_source'] == 'thorlabs_source_mcls1':
            self.log.warning('Using monochromatic MCLS1 source.  Overriding wavelength list and using only 640 nm.')
            wavelengths = [638.0]

        self.jacobian_filenames = {wavelength: jacobian_filenames[n] for n, wavelength in enumerate(wavelengths)}
        self.probe_filenames = {wavelength: probe_filenames[n] for n, wavelength in enumerate(wavelengths)}

        self.nd_direct = {wavelength: nd_direct[n] for n, wavelength in enumerate(wavelengths)}
        self.nd_coron = {wavelength: nd_coron[n] for n, wavelength in enumerate(wavelengths)}

        # Equally weight all wavelengths unless otherwise specified
        if control_weights is None:
            self.control_weights = np.ones(len(self.jacobian_filenames))
        else:
            self.control_weights = control_weights

        self.control_weights = {wavelength: self.control_weights[n] for n, wavelength in enumerate(wavelengths)}

        # Assume the input spectrum is uniform with wavelength unless otherwise specified
        if spectral_weights is None:
            self.spectral_weights = np.ones(len(self.jacobian_filenames))
        else:
            self.spectral_weights = spectral_weights

        self.spectral_weights = {wavelength: self.spectral_weights[n] for n, wavelength in enumerate(wavelengths)}

        self.wavelengths = wavelengths
        self.jacobians = {}
        self.probes = {}
        self.H_invs = {}

        # Iterate over provided Jacobians for each wavelength
        for wavelength in self.wavelengths:
            try:
                self.log.info(f'Reading Jacobian from {self.jacobian_filenames[wavelength]} for {wavelength} nm...')
                print(f'Reading Jacobian from {self.jacobian_filenames[wavelength]} for {wavelength} nm...')
                # self.wavelengths.append(wavelen)

                self.jacobians[wavelength] = hcipy.read_fits(self.jacobian_filenames[wavelength])
            except Exception as e:
                raise RuntimeError("Can't read Jacobian from {}.".format(self.jacobian_filenames[wavelength])) from e

            # Read dark zone geometry, probes, and obs matrix all in from extensions in the same file
            with fits.open(self.probe_filenames[wavelength]) as probe_info:
                self.log.info("Loading Dark Zone geometry from {}".format(self.probe_filenames[wavelength]))

                # Assume the dark zone regions are the same independent of wavelength. The code reads them in anyway redundantly at
                # each wavelength for now - ugly but easy and it works.
                self.dark_zone = hcipy.Field(np.asarray(probe_info['DARK_ZONE'].data, bool).ravel(), stroke_min.focal_grid)
                self.dark_zone_probe = hcipy.Field(np.asarray(probe_info['DARK_ZONE_PROBE'].data, bool).ravel(), stroke_min.focal_grid)

                self.log.info("Loading probe DM shapes from {}".format(self.probe_filenames[wavelength]))
                self.probes[wavelength] = probe_info['PROBES'].data

                self.log.info("Loading observation matrix from {}".format(self.probe_filenames[wavelength]))
                self.H_invs[wavelength] = probe_info['OBS_MATRIX'].data
                # # Turn observation matrix into Field so that we can use field_dot later when estimating electric field
                # self.H_invs[wavelen] = hcipy.Field(self.H_invs[wavelen], stroke_min.focal_grid)

                self.dz_rin = probe_info[0].header.get('DZ_RIN', '?')
                self.dz_rout = probe_info[0].header.get('DZ_ROUT', '?')
                self.probe_amp = probe_info[0].header.get('PROBEAMP', '?')

        self.num_iterations = num_iterations
        self.num_exposures = num_exposures
        self.exposure_time_coron = exposure_time_coron
        self.exposure_time_direct = exposure_time_direct
        self.use_dm2 = use_dm2

        # Cut Jacobian in half if using only DM1
        if not self.use_dm2:
            for wavelength in self.jacobians:
                self.jacobians[wavelength] = self.jacobians[wavelength][:stroke_min.num_actuators, :]

        self.gamma = gamma
        self.control_gain = control_gain
        self.auto_adjust_gamma = auto_adjust_gamma
        self.direct_every = direct_every
        self.resume = resume
        self.dm_command_dir_to_restore = dm_command_dir_to_restore
        self.autoscale_e_field = autoscale_e_field
        self.dm_calibration_fudge = dm_calibration_fudge
        self.correction = np.zeros(stroke_min.num_actuators*2, float)
        self.prior_correction = np.zeros(stroke_min.num_actuators*2, float)
        self.git_label = util.git_description()
        self.perfect_knowledge_mode = perfect_knowledge_mode

        if self.resume and self.auto_adjust_gamma:
            self.log.warning("Auto adjust gamma is not reliable with resume=True. Disabling auto adjust gamma.")
            self.auto_adjust_gamma = False

        self.dm1_actuators, self.dm2_actuators = self.get_initial_dm_commands()
        self.mu_start = mu_start

        # Values for diagnostic plots
        # In broadband, some of these need to be dicts over wavelength
        self.e_field_scale_factors = {wavelength: [] for wavelength in wavelengths}
        self.mean_contrasts_image = []  # keep just one of these, it will be broadband (eventually)
        self.mean_contrasts_pairwise = []
        self.mean_contrasts_probe = []
        self.predicted_contrasts = []
        self.predicted_contrast_deltas = []
        self.measured_contrast_deltas = []
        self.estimated_incoherent_backgrounds = []

        # Initialize output path and logging
        self.output_path = util.create_data_path(suffix=self.suffix)
        util.setup_hicat_logging(self.output_path, self.suffix)
        print("LOGGING: "+self.output_path+"  "+self.suffix)

        # Before doing anything more interesting, save a copy of the probes to disk
        # TODO: if self.file_mode: HICAT-817
        #self.save_probes()

    def take_exposure(self, devices, exposure_type, wavelength, initial_path, flux_attenuation_factor=1., suffix=None,
                      dm1_actuators=None, dm2_actuators=None, exposure_time=None):

        """
        Take an exposure on HiCAT.

        :param devices: handles to HiCAT hardware
        :param exposure_type: 'coron' or 'direct'
        :param wavelength: imaging wavelength, in nm
        :param initial_path: root path on disk where raw data is saved
        :param flux_attenuation_factor: float, flux attenuation factor, empirically determined, equals 1. for coron by definition (has no neutral density filter)
        :param suffix: string, appends this to the end of the timestamp, passed to take_exposure_hicat()
        :param dm1_actuators: array, DM1 actuator vector, in nm, passed to take_exposure_hicat()
        :param dm2_actuators: array, DM2 actuator vector, in nm, passed to take_exposure_hicat()
        :param exposure_time: float, exposure time in microsec, passed to take_exposure_hicat()
        :return: numpy array and header
        """
        if dm1_actuators is None:
            dm1_actuators = self.dm1_actuators

        if dm2_actuators is None:
            dm2_actuators = self.dm2_actuators

        if exposure_time is None:
            exposure_time = self.exposure_time_direct if exposure_type == 'direct' else self.exposure_time_coron

        # Only move filter wheel if we are using a broadband source. The MCLS1 is monochromatic.
        # This is done here rather than inside take_exposure_hicat because not every script that uses
        # take_exposure_hicat needs broadband functionality.
        if CONFIG_INI['testbed']['laser_source'] == 'light_source_assembly':

            if exposure_type == 'coron':
                nd_filter_set = self.nd_coron
            else:
                nd_filter_set = self.nd_direct

            move_filter(wavelength=int(np.rint(wavelength)), nd=nd_filter_set[wavelength], devices=devices)

        image, header = stroke_min.take_exposure_hicat(
            dm1_actuators, dm2_actuators, devices, wavelength=wavelength,
            exposure_type=exposure_type, exposure_time=exposure_time,
            initial_path=initial_path, num_exposures=self.num_exposures, suffix=suffix,
            file_mode=self.file_mode, raw_skip=self.raw_skip)

        # For coronagraphic images, this factor is 1 by definition
        if exposure_type == 'direct':
            image *= flux_attenuation_factor

        # Add flux factor to header, both on disk as well as in local variable
        # Find latest subdir - latest modified, not necessarily created, but should suffice for this application
        header['ATTENFAC'] = flux_attenuation_factor
        if self.file_mode:
            latest_dir = os.path.dirname(header["PATH"])
            for processed_im in ['*cal.fits', '*bin.fits']:
                search_str = os.path.join(latest_dir, processed_im)
                file_path = glob.glob(search_str)
                if not file_path:
                    raise FileNotFoundError("Failed: glob.glob('{search_str}')")
                fits.setval(filename=file_path[0], keyword='ATTENFAC', value=flux_attenuation_factor)

        return image, header

    def compute_broadband_weighted_mean(self, quantity, weights):
        """
        Compute a weighted average of the elements of a dictionary index by wavelength.

        :param quantity: dictionary whose keys are wavelengths
        :param weights: list of weights.  Assumed to have the same ordering as self.wavelengths
        """
        return sum(quantity[wavelength] * weights[wavelength] for wavelength in self.wavelengths) / len(self.wavelengths)

    def experiment(self):
        self.H_invs = {key: hcipy.Field(self.H_invs[key], stroke_min.focal_grid) for key in self.H_invs}
        # Initialize the testbed devices once, to reduce overhead of opening/intializing
        # each one for each exposure.
        with testbed.laser_source() as laser, \
                testbed.dm_controller() as dm, \
                testbed.motor_controller() as motor_controller, \
                testbed.imaging_apodizer_picomotor() as imaging_apodizer_picomotor, \
                testbed.ta_apodizer_picomotor() as ta_apodizer_picomotor, \
                testbed.ta_quadcell_picomotor() as ta_quadcell_picomotor, \
                testbed.beam_dump() as beam_dump, \
                testbed.imaging_camera() as cam, \
                testbed.pupil_camera() as pupilcam, \
                testbed.target_acquisition_camera() as ta_cam, \
                testbed.color_wheel() as color_wheel, \
                testbed.nd_wheel() as nd_wheel:

            devices = {'laser': laser,
                       'dm': dm,
                       'motor_controller': motor_controller,
                       'imaging_pico': (1, 2, imaging_apodizer_picomotor),
                       'apodizer_pico': (1, 2, ta_apodizer_picomotor),
                       'quadcell_pico': (3, 4, ta_quadcell_picomotor),
                       'beam_dump': beam_dump,
                       'imaging_camera': cam,
                       'pupil_camera': pupilcam,
                       'ta_camera': ta_cam,
                       'color_wheel': color_wheel,
                       'nd_wheel': nd_wheel}

            # Calculate flux attenuation factor (involves taking images)
            # For coronagraphic images, this factor is 1 by definition
            if not sim and CONFIG_INI.get('testbed', 'laser_source') == 'light_source_assembly':

                # Get optimized exposure times for photometry based on whether apodizer is used or not
                if CONFIG_INI.get('testbed', 'apodizer') == 'no_apodizer':
                    exp_time_direct_flux_norm = CONFIG_INI.getfloat('calibration', 'flux_norm_exp_time_direct_clc')
                    exp_time_coron_flux_norm = exp_time_direct_flux_norm / 20    # the currenlty used ND filter for coron ("9_percent") attenuates by about a facor of 10
                else:
                    exp_time_direct_flux_norm = CONFIG_INI.getfloat('calibration', 'flux_norm_exp_time_direct_aplc') #TODO: revisit this when in APLC mode on hardware (HiCAT-764)
                    exp_time_coron_flux_norm = exp_time_direct_flux_norm / 10

                # TODO: Add file_mode and raw_skip params to this func. Might we always want to save these?
                flux_norm_dir = stroke_min.capture_flux_attenuation_data(wavelengths=self.wavelengths,
                                                                         exp_dir=exp_time_direct_flux_norm,
                                                                         exp_coron=exp_time_coron_flux_norm,
                                                                         out_path=self.output_path,
                                                                         nd_direct=self.nd_direct,
                                                                         nd_coron=self.nd_coron,
                                                                         devices=devices,
                                                                         dm1_act=self.dm1_actuators,
                                                                         dm2_act=self.dm2_actuators,
                                                                         num_exp=self.num_exposures,
                                                                         file_mode=self.file_mode,
                                                                         raw_skip=self.raw_skip)
            else:
                flux_norm_dir = {}
                for wavelength in self.wavelengths:
                    flux_norm_dir[wavelength] = 1
            self.log.info("Flux normalization factors are: {}".format(flux_norm_dir))

            # Take "before" images
            initial_path = os.path.join(self.output_path, 'before')
            exposure_kwargs = {'initial_path': initial_path,
                               'num_exposures': self.num_exposures}

            # In the broadband code, many quantities need to be either lists per wavelength or dicts per wavelength
            # In this implementation we choose dicts.
            direct_maxes = {}
            images_direct = {}
            images_before = {}
            images_after = {}

            # Take starting reference images, in direct and coron, per each wavelength
            # Note, switching direct<->coron is much slower than filter wheel changes, so
            # for efficiency we should change the FPM position the minimum number of times
            for wavelength in self.wavelengths:
                images_direct[wavelength], _ = self.take_exposure(devices, 'direct', wavelength, initial_path, flux_norm_dir[wavelength])
                direct_maxes[wavelength] = images_direct[wavelength].max()

            for wavelength in self.wavelengths:
                images_before[wavelength], _ = self.take_exposure(devices, 'coron', wavelength, initial_path)
                images_before[wavelength] /= direct_maxes[wavelength]
                images_after[wavelength] = images_before[wavelength]

            # Compute broadband image as the average over wavelength, weighted by the spectral flux at each wavelength
            broadband_image_before = self.compute_broadband_weighted_mean(images_before, self.spectral_weights)
            broadband_image_after = broadband_image_before

            # Set up plot writing infrastructure
            self.init_strokemin_plots()
            self.mean_contrasts_image.append(np.mean(broadband_image_before[self.dark_zone]))
            
            # Instantiate TA Controller and run initial centering
            ta_controller = TargetAcquisition(devices, self.output_path, use_closed_loop=False)
            ta_controller.run_full_ta()

            # Main body of control loop
            for i in range(self.num_iterations):
                # Initialize empty dictionary.  This contains E-field estimates indexed by wavelength, and is
                # overwritten in each control iteration
                E_estimateds = {}
                mean_contrast_pairwise = {}
                mean_contrast_probe = {}
                probe_examples = {}

                self.log.info("Pairwise sensing and stroke minimization, iteration {}".format(i))
                
                # Check for any drifts and correct 
                ta_controller.run_smart_ta_loop()

                # Create a new output subfolder for each iteration
                initial_path = os.path.join(self.output_path, 'iter{:04d}'.format(i))

                # Make another exposure function with the bound/unbound arguments needed in the pairwise estimator
                def take_exposure_pairwise(dm1_actuators, dm2_actuators, suffix, wavelength):
                    return self.take_exposure(devices,
                                              exposure_type='coron',
                                              wavelength=wavelength,
                                              initial_path=initial_path,
                                              suffix=suffix,
                                              dm1_actuators=dm1_actuators,
                                              dm2_actuators=dm2_actuators)

                # Electric field estimation.  This covers several cases:
                #   - If we are in "perfect knowledge" mode, which only works in simulation, compute the true electric fields
                #   - If not, but the control weight for the wavelength is zero, then we just return zero to avoid taking pairwise data that is not used
                #     in control anyways.
                #   - In all other situations, take a pairwise estimate.
                for wavelength in self.wavelengths:
                    images_before[wavelength] = images_after[wavelength]

                    if self.perfect_knowledge_mode and sim:
                        self.compute_true_e_fields(E_estimateds, exposure_kwargs, initial_path, wavelength)
                    else:
                        if self.control_weights[wavelength] == 0:
                            E_estimateds[wavelength] = hcipy.Field(np.zeros(stroke_min.focal_grid.size, dtype='complex'), stroke_min.focal_grid)
                            mean_contrast_probe[wavelength] = np.mean(np.abs(E_estimateds[wavelength][self.dark_zone]) ** 2)
                            probe_examples[wavelength] = images_before[wavelength]
                        else:
                            self.log.info(f'Estimating electric fields using pairwise probes at {wavelength} nm...')
                            E_estimateds[wavelength], probe_examples[wavelength] = stroke_min.take_electric_field_pairwise(
                                self.dm1_actuators,
                                self.dm2_actuators,
                                take_exposure_pairwise,
                                devices,
                                self.H_invs[wavelength],
                                self.probes[wavelength],
                                self.dark_zone,
                                images_direct[wavelength],
                                initial_path=exposure_kwargs['initial_path'],
                                current_contrast=self.mean_contrasts_image[-1] if i>0 else None,
                                probe_amplitude=self.probe_amp,
                                wavelength=wavelength,
                                file_mode=self.file_mode)

                            # TODO: if self.file_mode: HICAT-817
                            hicat.util.save_complex(f"E_estimated_unscaled_{wavelength}nm.fits", E_estimateds[wavelength], exposure_kwargs['initial_path'])

                            mean_contrast_probe[wavelength] = np.mean(probe_examples[wavelength][self.dark_zone])

                            if self.autoscale_e_field:
                                # automatically scale the estimated E field to match the prior image contrast
                                expected_contrast = self.mean_contrasts_image[-1]
                                estimated_contrast = np.mean(np.abs(E_estimateds[wavelength][self.dark_zone]) ** 2)
                                contrast_ratio = expected_contrast/estimated_contrast
                                self.log.info("Scaling estimated e field by {} to match image contrast ".format(np.sqrt(contrast_ratio)))
                                self.e_field_scale_factors[wavelength].append(np.sqrt(contrast_ratio))
                            else:
                                self.e_field_scale_factors[wavelength].append(1.)

                            E_estimateds[wavelength] *= self.e_field_scale_factors[wavelength][-1]

                    # Save raw contrast from pairwise image
                    mean_contrast_pairwise[wavelength] = np.mean(np.abs(E_estimateds[wavelength][self.dark_zone]) ** 2)

                self.mean_contrasts_pairwise.append(self.compute_broadband_weighted_mean(mean_contrast_pairwise, self.control_weights))
                self.mean_contrasts_probe.append(self.compute_broadband_weighted_mean(mean_contrast_probe, self.control_weights))
                self.probe_example = self.compute_broadband_weighted_mean(probe_examples, self.control_weights)

                self.log.info('Calculating stroke min correction, iteration {}...'.format(i))

                gamma = self.adjust_gamma(i) if self.auto_adjust_gamma else self.gamma

                # Find the required DM update here
                correction, self.mu_start, predicted_contrast, predicted_contrast_drop = self.compute_correction(
                    E_estimateds, gamma, devices, exposure_kwargs)

                # Adjust correction and predicted results for the control gain:
                correction *= self.control_gain
                predicted_contrast += (1 - self.control_gain) * np.abs(predicted_contrast_drop)
                predicted_contrast_drop *= self.control_gain

                self.prior_correction = self.correction     # save for use in plots
                self.correction = correction                # save for use in plots
                self.predicted_contrasts.append(predicted_contrast) # save for use in plots
                self.predicted_contrast_deltas.append(predicted_contrast_drop) # save for use in plots

                self.log.info("Starting contrast from pairwise for iteration {}: {}".format(i, self.mean_contrasts_pairwise[-1]))
                self.log.info("Iteration {} used mu = {}".format(i, self.mu_start))
                self.log.info("Predicted contrast after this iteration: {}".format(self.predicted_contrasts[-1]))
                self.log.info("Predicted contrast change this iteration: {}".format(self.predicted_contrast_deltas[-1]))

                # Update DM actuators
                self.sanity_check(correction)
                dm1_correction, dm2_correction = stroke_min.split_command_vector(correction, self.use_dm2)
                self.dm1_actuators -= dm1_correction
                self.dm2_actuators -= dm2_correction

                self.log.info('Taking post-correction coronagraphic images and pupil image...')

                self.latest_pupil_image = stroke_min.take_pupilcam_hicat(devices,
                                                                         num_exposures=1,
                                                                         initial_path=exposure_kwargs['initial_path'],
                                                                         file_mode=self.file_mode)[0]

                # Capture images after DM correction
                if np.mod(i, self.direct_every) == 0:
                    self.log.info('Taking direct images for comparison...')

                    for wavelength in self.wavelengths:
                        images_direct[wavelength], _ = self.take_exposure(devices, 'direct', wavelength, initial_path, flux_norm_dir[wavelength])
                        direct_maxes[wavelength] = images_direct[wavelength].max()

                for wavelength in self.wavelengths:
                    images_after[wavelength], _ = self.take_exposure(devices, 'coron', wavelength, initial_path)
                    images_after[wavelength] /= direct_maxes[wavelength]

                broadband_image_before = broadband_image_after
                broadband_image_after = self.compute_broadband_weighted_mean(images_after, self.spectral_weights)

                # Save more data for plotting
                self.mean_contrasts_image.append(np.mean(broadband_image_after[self.dark_zone]))  # Mean dark-zone contrast after correction
                self.measured_contrast_deltas.append(self.mean_contrasts_image[-1] - self.mean_contrasts_image[-2])  # Change in measured contrast
                self.log.info("===> Measured contrast drop this iteration: {}".format(self.measured_contrast_deltas[-1]))

                I_estimateds = {wavelength: np.abs(E_estimated) ** 2 for wavelength, E_estimated in E_estimateds.items()}
                est_incoherent = np.abs(broadband_image_before - self.compute_broadband_weighted_mean(I_estimateds, self.control_weights))
                self.estimated_incoherent_backgrounds.append(np.mean(est_incoherent[self.dark_zone]))  # Estimated incoherent background

                # Make diagnostic plots
                self.show_strokemin_plot(broadband_image_before, broadband_image_after, self.dm1_actuators, self.dm2_actuators, E_estimateds)

    def compute_true_e_fields(self, E_estimateds, exposure_kwargs, initial_path, wavelength):
        """ Compute and save the true E-fields.  Only usable in simulation. """
        for apply_pipeline_binning, suffix in zip([False, True], ['cal', 'bin']):
            # Not binned
            E_sim_actual, _header = stroke_min.take_exposure_hicat_simulator(self.dm1_actuators,
                                                                             self.dm2_actuators,
                                                                             apply_pipeline_binning=apply_pipeline_binning,
                                                                             wavelength=wavelength,
                                                                             exposure_type='coronEfield',
                                                                             output_path=initial_path)  # E_actual is in sqrt(counts/sec)
            direct_sim, _header = stroke_min.take_exposure_hicat_simulator(self.dm1_actuators,
                                                                           self.dm2_actuators,
                                                                           apply_pipeline_binning=apply_pipeline_binning,
                                                                           wavelength=wavelength,
                                                                           exposure_type='direct',
                                                                           output_path=initial_path)
            E_sim_normalized = E_sim_actual / np.sqrt(direct_sim.max())
            # TODO: if self.file_mode: HICAT-817
            hicat.util.save_complex(f"E_actual_{suffix}_{wavelength}nm.fits", E_sim_normalized, exposure_kwargs['initial_path'])
            hicat.util.save_intensity(f"I_actual_from_sim_{suffix}_{wavelength}nm.fits", E_sim_normalized, exposure_kwargs['initial_path'])

            # Replace the pairwise estimate with the simulated binned E-field
            # Note that this relies on the binned E-field being computed last in the above loop
            estimate = hcipy.Field(np.zeros(stroke_min.focal_grid.size, dtype='complex'), stroke_min.focal_grid)
            estimate[self.dark_zone] = E_sim_normalized[self.dark_zone]
            E_estimateds[wavelength] = estimate

        return E_estimateds

    def get_initial_dm_commands(self):
        """ Initialize the DM actuator commands.  This is called in __init__()."""
        # Same as regular function except expected jacobian filenames in a list and only checks the first one
        if self.resume:
            dm1_actuators, dm2_actuators = self.restore_last_strokemin_dm_shapes(self.dm_command_dir_to_restore)
        else:
            # Check if Jacobian includes information on which DM state it is linearized around
            try:
                dm_settings = fits.getdata(self.jacobian_filenames[0], extname='DM_SETTINGS' )
                dm1_actuators = dm_settings[0]
                dm2_actuators = dm_settings[1]
            except KeyError:
                # no DM settings saved, therefore start with flat DMs
                dm1_actuators = np.zeros(stroke_min.num_actuators)
                dm2_actuators = np.zeros(stroke_min.num_actuators)

        return dm1_actuators, dm2_actuators

    # def show_contrast_vs_wavelength(self, images_after):
    #     fig, axs = plt.subplots(nrows=1, ncols=4, figsize=(22, 5), gridspec_kw={'wspace': 0.3})
    #     ax = axs[0]
    #     im = ax.imshow(images_after[self.wavelengths[0]], norm=colo)

    def show_strokemin_plot(self, image_before, image_after, dm1_actuators, dm2_actuators, E_estimateds):
        """ Create the quantities that will be displayed in the show_strokemin_plot() of the parent class """
        e_field_scale_factors = self.e_field_scale_factors

        self.e_field_scale_factors = self.e_field_scale_factors[self.wavelengths[0]]
        self.jacobian_filename = self.jacobian_filenames[self.wavelengths[0]]
        self.probe_filename = self.probe_filenames[self.wavelengths[0]]

        # Can only show E_estimated and I_estimated_from_E because parent class can only display a monochromatic field.
        # Computing a weighted mean of the field doesn't make sense because the E-fields at each wavelength are
        # mutually incoherent.
        super().show_strokemin_plot(image_before, image_after, dm1_actuators, dm2_actuators, E_estimateds[self.wavelengths[0]])

        self.e_field_scale_factors = e_field_scale_factors

    def compute_correction(self, E_estimateds, gamma, devices, exposure_kwargs):
        """
        Calculate the DM actuator correction for a given field estimate and contrast decrease factor.
        """

        correction, mu_start, predicted_contrast, predicted_contrast_drop = stroke_min.broadband_stroke_minimization(
            self.jacobians, E_estimateds, self.dark_zone, gamma, self.spectral_weights, self.control_weights,
            self.mu_start)

        return correction, mu_start, predicted_contrast, predicted_contrast_drop
