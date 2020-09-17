# flake8: noqa: E402
import hicat.simulators
sim = hicat.simulators.auto_enable_sim()

from hicat.config import CONFIG_INI

import numpy as np
import matplotlib.pyplot as plt
import os
import glob
from astropy.io import fits
import hcipy
import hicat.util
import datetime
import collections

from catkit.catkit_types import FpmPosition

from hicat.control.target_acq import MotorMount, TargetCamera, TargetAcquisition
from hicat.control.align_lyot import LyotStopAlignment
from hicat.hardware import testbed, testbed_state
import hicat.plotting.animation
from hicat.plotting import wfsc_plots
from hicat import util
from hicat.wfc_algorithms import wfsc_utils
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
    :param auto_num_exposures: If SNR/pix drops below target_snr_per_pix, increase the number of exposures
    :param target_snr_per_pix: Desired minimum SNR per pixel, averaged over the dark zone, in reduced, binned images.
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
    :param align_lyot_stop : Whether to align the Lyot Stop at the start of the experiment
    :param run_ta: Whether to run with target acquisition.
    """
    def __init__(self, wavelengths, jacobian_filenames, probe_filenames, num_iterations,
                 num_exposures=10,
                 exposure_time_coron=100000,
                 exposure_time_direct=100,
                 auto_expose={FpmPosition.coron: False, FpmPosition.direct: True},
                 use_dm2=False,
                 gamma=0.8,
                 auto_adjust_gamma=False,
                 control_gain=1.0,
                 autoscale_e_field=False,
                 auto_num_exposures=True,
                 target_snr_per_pix=10,
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
                 raw_skip=0,
                 align_lyot_stop=False,
                 run_ta=False):
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

                jac_hdr = fits.getheader((self.jacobian_filenames[wavelength]))
                if 'CRN_MODE' in jac_hdr:
                    if jac_hdr['CRN_MODE'] != wfsc_utils.current_mode:
                        raise RuntimeError(f"This jacobian file is for mode={jac_hdr['CRN_MODE']} but the system is"
                                           f" configured for mode {wfsc_utils.current_mode}: "
                                           f"filename {self.jacobian_filenames[wavelength]}")
            except Exception as e:
                raise RuntimeError("Can't read Jacobian from {}.".format(self.jacobian_filenames[wavelength])) from e

            # Read dark zone geometry, probes, and obs matrix all in from extensions in the same file
            with fits.open(self.probe_filenames[wavelength]) as probe_info:
                self.log.info("Loading Dark Zone geometry from {}".format(self.probe_filenames[wavelength]))

                # Assume the dark zone regions are the same independent of wavelength. The code reads them in anyway redundantly at
                # each wavelength for now - ugly but easy and it works.
                self.dark_zone = hcipy.Field(np.asarray(probe_info['DARK_ZONE'].data, bool).ravel(), wfsc_utils.focal_grid)
                self.dark_zone_probe = hcipy.Field(np.asarray(probe_info['DARK_ZONE_PROBE'].data, bool).ravel(), wfsc_utils.focal_grid)

                self.log.info("Loading probe DM shapes from {}".format(self.probe_filenames[wavelength]))
                self.probes[wavelength] = probe_info['PROBES'].data

                self.log.info("Loading observation matrix from {}".format(self.probe_filenames[wavelength]))
                self.H_invs[wavelength] = probe_info['OBS_MATRIX'].data
                # # Turn observation matrix into Field so that we can use field_dot later when estimating electric field
                # self.H_invs[wavelen] = hcipy.Field(self.H_invs[wavelen], wfsc_utils.focal_grid)

                self.dz_rin = probe_info[0].header.get('DZ_RIN', '?')
                self.dz_rout = probe_info[0].header.get('DZ_ROUT', '?')
                self.probe_amp = probe_info[0].header.get('PROBEAMP', '?')

        self.num_iterations = num_iterations
        self.num_exposures = num_exposures
        self.exposure_time_coron = exposure_time_coron
        self.exposure_time_direct = exposure_time_direct
        self.auto_expose = auto_expose
        self.auto_num_exposures = auto_num_exposures
        self.target_snr_per_pix = target_snr_per_pix
        self.use_dm2 = use_dm2

        # Cut Jacobian in half if using only DM1
        if not self.use_dm2:
            for wavelength in self.jacobians:
                self.jacobians[wavelength] = self.jacobians[wavelength][:wfsc_utils.num_actuators, :]

        self.gamma = gamma
        self.control_gain = control_gain
        self.auto_adjust_gamma = auto_adjust_gamma
        self.direct_every = direct_every
        self.resume = resume
        self.dm_command_dir_to_restore = dm_command_dir_to_restore
        self.autoscale_e_field = autoscale_e_field
        self.dm_calibration_fudge = dm_calibration_fudge
        self.correction = np.zeros(wfsc_utils.num_actuators * 2, float)
        self.prior_correction = np.zeros(wfsc_utils.num_actuators * 2, float)
        self.git_label = util.git_description()
        self.perfect_knowledge_mode = perfect_knowledge_mode
        self.align_lyot_stop = align_lyot_stop
        self.run_ta = run_ta

        # Metrics
        self.timestamp = []
        self.temp = []
        self.humidity = []

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

    def take_exposure(self,
                      devices,
                      exposure_type,
                      wavelength,
                      initial_path,
                      flux_attenuation_factor=1.,
                      suffix=None,
                      dm1_actuators=None,
                      dm2_actuators=None,
                      exposure_time=None,
                      auto_expose=None,
                      **kwargs):

        """
        Take an exposure on HiCAT.  This function binds some parameters to the general-purpose
        wfsc_utils.take_exposure_hicat_broadband() using object attributes.

        :param devices: handles to HiCAT hardware
        :param exposure_type: 'coron' or 'direct'
        :param wavelength: imaging wavelength, in nm
        :param initial_path: root path on disk where raw data is saved
        :param flux_attenuation_factor: float, flux attenuation factor, empirically determined, equals 1. for coron by definition (has no neutral density filter)
        :param suffix: string, appends this to the end of the timestamp, passed to take_exposure_hicat()
        :param dm1_actuators: array, DM1 actuator vector, in nm, passed to take_exposure_hicat()
        :param dm2_actuators: array, DM2 actuator vector, in nm, passed to take_exposure_hicat()
        :param exposure_time: float, exposure time in microsec, passed to take_exposure_hicat()
        :param auto_expose: bool or {catkit.catkit_types.FpmPosition: bool}, flag to enable auto exposure time correction.
        :return: numpy array and header
        """
        if dm1_actuators is None:
            dm1_actuators = self.dm1_actuators

        if dm2_actuators is None:
            dm2_actuators = self.dm2_actuators

        if exposure_time is None:
            exposure_time = self.exposure_time_direct if exposure_type == 'direct' else self.exposure_time_coron

        auto_expose = self.auto_expose if auto_expose is None else auto_expose

        if exposure_type == 'coron':
            nd_filter = self.nd_coron[wavelength]
        else:
            nd_filter = self.nd_direct[wavelength]

        return wfsc_utils.take_exposure_hicat_broadband(
            dm1_actuators,
            dm2_actuators,
            devices,
            nd_filter,
            flux_attenuation_factor,
            exposure_type,
            self.num_exposures,
            exposure_time,
            auto_expose,
            self.file_mode,
            self.raw_skip,
            initial_path,
            suffix,
            wavelength=wavelength,
            **kwargs
        )

    def compute_broadband_weighted_mean(self, quantity, weights):
        """
        Compute a weighted average of the elements of a dictionary index by wavelength.

        :param quantity: dictionary whose keys are wavelengths
        :param weights: list of weights.  Assumed to have the same ordering as self.wavelengths
        """
        return sum(quantity[wavelength] * weights[wavelength] for wavelength in self.wavelengths) / len(self.wavelengths)

    def experiment(self):
        self.H_invs = {key: hcipy.Field(self.H_invs[key], wfsc_utils.focal_grid) for key in self.H_invs}

        # Get cached devices, etc, that were instantiated (and connections opened) in HicatExperiment.pre_experiment().
        devices = testbed_state.devices.copy()
        ta_controller = testbed_state.cache["ta_controller"]

        # Calculate flux attenuation factor between direct+ND and coronagraphic images
        flux_norm_dir = wfsc_utils.capture_flux_attenuation_data(wavelengths=self.wavelengths,
                                                                 out_path=self.output_path,
                                                                 nd_direct=self.nd_direct,
                                                                 nd_coron=self.nd_coron,
                                                                 devices=devices,
                                                                 dm1_act=self.dm1_actuators,
                                                                 dm2_act=self.dm2_actuators,
                                                                 num_exp=self.num_exposures,
                                                                 file_mode=self.file_mode,
                                                                 raw_skip=self.raw_skip)

        # Take "before" images
        initial_path = os.path.join(self.output_path, 'before')
        exposure_kwargs = {'initial_path': initial_path,
                           'num_exposures': self.num_exposures}

        # In the broadband code, many quantities need to be either lists per wavelength or dicts per wavelength
        # In this implementation we choose dicts.
        direct_maxes = {}
        images_direct = {}
        self.images_before = {}
        self.images_after = {}
        self.estimated_darkzone_SNRs = {}
        self.estimated_probe_SNRs = {}
        self.broadband_images = []  # broadband images are however just a list

        # Take starting reference images, in direct and coron, per each wavelength
        # Note, switching direct<->coron is much slower than filter wheel changes, so
        # for efficiency we should change the FPM position the minimum number of times
        for wavelength in self.wavelengths:
            images_direct[wavelength], _ = self.take_exposure(devices, 'direct', wavelength, initial_path, flux_norm_dir[wavelength])
            direct_maxes[wavelength] = images_direct[wavelength].max()

        for wavelength in self.wavelengths:
            self.images_before[wavelength], header = self.take_exposure(devices, 'coron', wavelength, initial_path,
                                                                        dark_zone_mask=self.dark_zone)
            self.images_before[wavelength] /= direct_maxes[wavelength]
            self.images_after[wavelength] = self.images_before[wavelength]
            est_snr = header['SNR_DZ'] if header['SNR_DZ'] > 0 else np.nan  # alas, can't have NaN in FITS header keywords
            self.estimated_darkzone_SNRs[wavelength] = [est_snr]
            self.estimated_probe_SNRs[wavelength] = []

        # Compute broadband image as the average over wavelength, weighted by the spectral flux at each wavelength
        self.broadband_images.append(self.compute_broadband_weighted_mean(self.images_before, self.spectral_weights))

        # Set up plot writing infrastructure
        self.init_strokemin_plots()
        self.mean_contrasts_image.append(np.mean(self.broadband_images[-1][self.dark_zone]))
        self.collect_metrics(devices)

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
            if self.run_ta:
                # TODO: Are the filters in their optimal positions for TA?
                ta_controller.acquire_target(recover_from_coarse_misalignment=False)
            else:
                # Plot position of PSF centroid on TA camera.
                ta_controller.distance_to_target(TargetCamera.TA, check_threshold=False)

            # Create a new output subfolder for each iteration
            initial_path = os.path.join(self.output_path, 'iter{:04d}'.format(i))

            # Make another exposure function with the bound/unbound arguments needed in the pairwise estimator
            def take_exposure_pairwise(dm1_actuators, dm2_actuators, suffix, wavelength, **kwargs):
                return self.take_exposure(devices,
                                          exposure_type='coron',
                                          wavelength=wavelength,
                                          initial_path=initial_path,
                                          suffix=suffix,
                                          dm1_actuators=dm1_actuators,
                                          dm2_actuators=dm2_actuators, **kwargs)

            # Electric field estimation.  This covers several cases:
            #   - If we are in "perfect knowledge" mode, which only works in simulation, compute the true electric fields
            #   - If not, but the control weight for the wavelength is zero, then we just return zero to avoid taking pairwise data that is not used
            #     in control anyways.
            #   - In all other situations, take a pairwise estimate.
            for wavelength in self.wavelengths:
                self.images_before[wavelength] = self.images_after[wavelength]

                if self.perfect_knowledge_mode and sim:
                    self.compute_true_e_fields(E_estimateds, exposure_kwargs, initial_path, wavelength)
                else:
                    if self.control_weights[wavelength] == 0:
                        E_estimateds[wavelength] = hcipy.Field(np.zeros(wfsc_utils.focal_grid.size, dtype='complex'), wfsc_utils.focal_grid)
                        mean_contrast_probe[wavelength] = np.mean(np.abs(E_estimateds[wavelength
                                                                         ][self.dark_zone]) ** 2)
                        probe_examples[wavelength] = self.images_before[wavelength]
                    else:
                        self.log.info(f'Estimating electric fields using pairwise probes at '
                                      f'{wavelength} nm...')
                        E_estimateds[wavelength], probe_examples[wavelength], probe_snr = wfsc_utils.take_electric_field_pairwise(
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

                        self.estimated_probe_SNRs[wavelength].append(probe_snr)
                        # TODO: if self.file_mode: HICAT-817
                        hicat.util.save_complex(f"E_estimated_unscaled_{int(wavelength)}nm.fits", E_estimateds[wavelength], initial_path)

                        mean_contrast_probe[wavelength] = np.mean(probe_examples[wavelength][self.dark_zone])

                        if self.autoscale_e_field:
                            # automatically scale the estimated E field to match the prior image contrast, at this wavelength
                            expected_contrast = np.mean(self.images_before[wavelength][self.dark_zone])
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
            dm1_correction, dm2_correction = wfsc_utils.split_command_vector(correction, self.use_dm2)
            self.dm1_actuators -= dm1_correction
            self.dm2_actuators -= dm2_correction

            self.log.info('Taking post-correction pupil image...')

            self.latest_pupil_image = wfsc_utils.take_pupilcam_hicat(devices,
                                                                     num_exposures=1,
                                                                     initial_path=exposure_kwargs['initial_path'],
                                                                     file_mode=self.file_mode)[0]

            # Capture images after DM correction
            if np.mod(i, self.direct_every) == 0:
                self.log.info('Taking direct images for comparison...')

                for wavelength in self.wavelengths:
                    images_direct[wavelength], _ = self.take_exposure(devices, 'direct', wavelength, initial_path, flux_norm_dir[wavelength])
                    direct_maxes[wavelength] = images_direct[wavelength].max()

            self.log.info('Taking post-correction coronagraphic images...')
            for wavelength in self.wavelengths:
                self.images_after[wavelength], header = self.take_exposure(devices, 'coron', wavelength, initial_path,
                                                                           dark_zone_mask=self.dark_zone)
                self.images_after[wavelength] /= direct_maxes[wavelength]
                est_snr = header['SNR_DZ'] if header['SNR_DZ'] > 0 else np.nan  # alas, can't have NaN in FITS header keywords
                self.estimated_darkzone_SNRs[wavelength].append(est_snr)

            self.broadband_images.append(self.compute_broadband_weighted_mean(self.images_after, self.spectral_weights))

            # Save more data for plotting
            self.mean_contrasts_image.append(np.mean(self.broadband_images[-1][self.dark_zone]))  # Mean dark-zone contrast after correction
            self.collect_metrics(devices)
            self.measured_contrast_deltas.append(self.mean_contrasts_image[-1] - self.mean_contrasts_image[-2])  # Change in measured contrast
            self.log.info("===> Measured contrast drop this iteration: {}".format(self.measured_contrast_deltas[-1]))

            I_estimateds = {wavelength: np.abs(E_estimated) ** 2 for wavelength, E_estimated in E_estimateds.items()}
            est_incoherent = np.abs(self.broadband_images[-2] - self.compute_broadband_weighted_mean(I_estimateds, self.control_weights))
            self.estimated_incoherent_backgrounds.append(np.mean(est_incoherent[self.dark_zone]))  # Estimated incoherent background

            # Make diagnostic plots
            self.show_status_plots(self.broadband_images[-2], self.broadband_images[-1], self.dm1_actuators, self.dm2_actuators, E_estimateds)

            # Check SNR, and if necessary adjust exposure settings before next iteration
            self.check_snr()

    def compute_true_e_fields(self, E_estimateds, exposure_kwargs, initial_path, wavelength):
        """ Compute and save the true E-fields.  Only usable in simulation. """
        for apply_pipeline_binning, suffix in zip([False, True], ['cal', 'bin']):
            # Not binned
            E_sim_actual, _header = wfsc_utils.take_exposure_hicat_simulator(self.dm1_actuators,
                                                                             self.dm2_actuators,
                                                                             apply_pipeline_binning=apply_pipeline_binning,
                                                                             wavelength=wavelength,
                                                                             exposure_type='coronEfield',
                                                                             output_path=initial_path)  # E_actual is in sqrt(counts/sec)
            direct_sim, _header = wfsc_utils.take_exposure_hicat_simulator(self.dm1_actuators,
                                                                           self.dm2_actuators,
                                                                           apply_pipeline_binning=apply_pipeline_binning,
                                                                           wavelength=wavelength,
                                                                           exposure_type='direct',
                                                                           output_path=initial_path)
            E_sim_normalized = E_sim_actual / np.sqrt(direct_sim.max())
            # TODO: if self.file_mode: HICAT-817
            hicat.util.save_complex(f"E_actual_{suffix}_{wavelength}nm.fits", E_sim_normalized, exposure_kwargs['initial_path'])
            hicat.util.save_intensity(f"I_actual_from_sim_{suffix}_{wavelength}nm.fits",
                                      E_sim_normalized, exposure_kwargs['initial_path'])

            # Replace the pairwise estimate with the simulated binned E-field
            # Note that this relies on the binned E-field being computed last in the above loop
            estimate = hcipy.Field(np.zeros(wfsc_utils.focal_grid.size, dtype='complex'), wfsc_utils.focal_grid)
            estimate[self.dark_zone] = E_sim_normalized[self.dark_zone]
            E_estimateds[wavelength] = estimate

        return E_estimateds

    def get_initial_dm_commands(self):
        """ Initialize the DM actuator commands.  This is called in __init__()."""
        # Same as regular function except expected jacobian filenames in a list and only checks the first one
        if self.resume:
            dm1_actuators, dm2_actuators = wfsc_utils.load_dm_commands(
                self.dm_command_dir_to_restore,
                self.suffix,
                min_iterations_to_resume=10
            )
        else:
            # Check if Jacobian includes information on which DM state it is linearized around
            try:
                dm_settings = fits.getdata(self.jacobian_filenames[0], extname='DM_SETTINGS' )
                dm1_actuators = dm_settings[0]
                dm2_actuators = dm_settings[1]
            except KeyError:
                # no DM settings saved, therefore start with flat DMs
                dm1_actuators = np.zeros(wfsc_utils.num_actuators)
                dm2_actuators = np.zeros(wfsc_utils.num_actuators)

        return dm1_actuators, dm2_actuators

    def show_status_plots(self,  image_before, image_after, dm1_actuators, dm2_actuators, E_estimateds):
        self.log.info(f"Producing status plots.")
        super().show_status_plots( image_before, image_after, dm1_actuators, dm2_actuators, E_estimateds)
        self.show_broadband_strokemin_plot(E_estimateds)

    def show_strokemin_plot(self, image_before, image_after, dm1_actuators, dm2_actuators, E_estimateds):
        """ Create the quantities that will be displayed in the show_strokemin_plot() of the parent class """
        e_field_scale_factors = self.e_field_scale_factors
        estimated_darkzone_snrs = self.estimated_darkzone_SNRs
        estimated_probe_snrs = self.estimated_probe_SNRs

        self.e_field_scale_factors = self.e_field_scale_factors[self.wavelengths[0]]
        self.estimated_darkzone_SNRs = self.estimated_darkzone_SNRs[self.wavelengths[0]]
        self.estimated_probe_SNRs = self.estimated_probe_SNRs[self.wavelengths[0]]
        self.jacobian_filename = self.jacobian_filenames[self.wavelengths[0]]
        self.probe_filename = self.probe_filenames[self.wavelengths[0]]

        # Can only show E_estimated and I_estimated_from_E because parent class can only display a monochromatic field.
        # Computing a weighted mean of the field doesn't make sense because the E-fields at each wavelength are
        # mutually incoherent.
        super().show_strokemin_plot(image_before, image_after, dm1_actuators, dm2_actuators, E_estimateds[self.wavelengths[0]])

        self.e_field_scale_factors = e_field_scale_factors
        self.estimated_darkzone_SNRs = estimated_darkzone_snrs
        self.estimated_probe_SNRs = estimated_probe_snrs

    def compute_correction(self, E_estimateds, gamma, devices, exposure_kwargs):
        """
        Calculate the DM actuator correction for a given field estimate and contrast decrease factor.
        """

        correction, mu_start, predicted_contrast, predicted_contrast_drop = wfsc_utils.broadband_stroke_minimization(
            self.jacobians, E_estimateds, self.dark_zone, gamma, self.spectral_weights, self.control_weights,
            self.mu_start)

        return correction, mu_start, predicted_contrast, predicted_contrast_drop

    def check_snr(self):
        """
        # Before next iteration, check SNR in image. If it's too low, increase number of exposures.
        # We should do this _after_ the plot, so the plot labels still reflect the values used
        # in this iteration.
        """

        min_last_probe_snr = np.min([self.estimated_probe_SNRs[wl][-1] for wl in self.wavelengths])
        min_last_dz_snr = np.min([self.estimated_darkzone_SNRs[wl][-1] for wl in self.wavelengths])
        self.log.info(
            "Estimated SNR in faintest probe image is {:.2f} per pix, using {} exposures.".format(min_last_probe_snr,
                                                                                         self.num_exposures))
        self.log.info("Estimated SNR in faintest dark zone image is {:.2f} per pix, using {} exposures.".format(min_last_dz_snr,
                                                                                                       self.num_exposures))
        if self.auto_num_exposures and (min_last_probe_snr < self.target_snr_per_pix) or (min_last_dz_snr < self.target_snr_per_pix):

            self.num_exposures *= 2
            self.log.warning(
                ("SNR per pixel in dark zone or probe has dropped below {}. Doubling number of exposures to compensate. "
                 "New num_exposures = {}").format(self.target_snr_per_pix, self.num_exposures))

    def init_strokemin_plots(self, output_path=None):
        """ Set up the infrastructure for writing out plots
        in particular the GifWriter object and output directory
        """
        # Init the standard diagnostic plots, which are a holdover from monochromatic
        super().init_strokemin_plots(output_path=output_path)
        # Init a second set of plots, for multiwavelength broadband output
        output_path_broadband = os.path.join(self.output_path, 'stroke_min_broadband.gif')
        self.log.info("Broadband diagnostic images will be saved to " + output_path_broadband)
        self.movie_writer_broadband = hicat.plotting.animation.GifWriter(output_path_broadband, framerate=2, cleanup=False)
        # setup a store for some extra data to be used in the broadband plot
        self._bb_plot_history = collections.deque(maxlen=10)

    def show_broadband_strokemin_plot(self, E_estimateds):
        """ Diagnostic status plot for all wavelengths being sensed.

        Note, only call this after calling init_strokemin_plots.
        """
        iteration = len(self.mean_contrasts_image)
        gamma = self.adjust_gamma(iteration) if self.auto_adjust_gamma else self.gamma
        wfsc_plots.make_broadband_control_loop_status_plot(
            self.wavelengths,
            self.images_before,
            self.images_after,
            self.broadband_images,
            E_estimateds,
            self._bb_plot_history,
            self.probe_example,
            self.dark_zone,
            self.dz_rin,
            self.dz_rout,
            gamma,
            self.control_gain,
            self.jacobian_filenames[self.wavelengths[0]],
            self.probe_filenames[self.wavelengths[0]],
            len(self.probes),
            self.probe_amp,
            self.num_exposures,
            self.exposure_time_coron,
            self.exposure_time_direct,
            self.mean_contrasts_image,
            self.mean_contrasts_probe,
            self.mean_contrasts_pairwise,
            self.predicted_contrasts,
            self.e_field_scale_factors,
            self.measured_contrast_deltas,
            self.predicted_contrast_deltas,
            self.estimated_incoherent_backgrounds,
            self.estimated_probe_SNRs,
            self.estimated_darkzone_SNRs,
            self.git_label,
            self.output_path
        )
        self.movie_writer_broadband.add_frame()

        plt.close()
