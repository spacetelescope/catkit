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
        self.auto_expose = auto_expose
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

    def take_exposure(self, devices, exposure_type, wavelength, initial_path, flux_attenuation_factor=1., suffix=None,
                      dm1_actuators=None, dm2_actuators=None, exposure_time=None, auto_expose=None):

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
            exposure_type=exposure_type, exposure_time=exposure_time, auto_expose=auto_expose,
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
                testbed.apodizer_picomotor_mount() as apodizer_picomotor_mount, \
                testbed.quadcell_picomotor_mount() as quadcell_picomotor_mount, \
                testbed.beam_dump() as beam_dump, \
                testbed.imaging_camera() as cam, \
                testbed.pupil_camera() as pupilcam, \
                testbed.temp_sensor(config_id="aux_temperature_sensor") as temp_sensor, \
                testbed.target_acquisition_camera() as ta_cam, \
                testbed.color_wheel() as color_wheel, \
                testbed.nd_wheel() as nd_wheel:

            devices = {'laser': laser,
                       'dm': dm,
                       'motor_controller': motor_controller,
                       'beam_dump': beam_dump,
                       'imaging_camera': cam,
                       'pupil_camera': pupilcam,
                       'temp_sensor': temp_sensor,
                       'color_wheel': color_wheel,
                       'nd_wheel': nd_wheel}

            # Instantiate TA Controller and run initial centering
            ta_devices = {'picomotors': {MotorMount.APODIZER: apodizer_picomotor_mount,
                                         MotorMount.QUAD_CELL: quadcell_picomotor_mount},
                           'beam_dump': beam_dump,
                           "cameras": {TargetCamera.SCI: cam,
                                       TargetCamera.TA: ta_cam}}

            with TargetAcquisition(ta_devices,
                                   self.output_path,
                                   use_closed_loop=False,
                                   n_exposures=20,
                                   exposure_period=5,
                                   target_pixel_tolerance={TargetCamera.TA: 2, TargetCamera.SCI: 25}) as ta_controller:

                # Flatten DMs before attempting initial target acquisition.
                from catkit.hardware.boston.commands import flat_command
                import copy
                ta_dm_flat = flat_command(bias=False, flat_map=True)
                devices["dm"].apply_shape_to_both(ta_dm_flat, copy.deepcopy(ta_dm_flat))
                # Now setup filter wheels.
                move_filter(wavelength=640,
                            nd="clear_1",
                            devices={"color_wheel": devices["color_wheel"], "nd_wheel": devices["nd_wheel"]})
                if self.run_ta:
                    ta_controller.acquire_target(coarse_align=True)
                else:
                    # Plot position of PSF centroid on TA camera.
                    ta_controller.distance_to_target(TargetCamera.TA)

                # Calculate flux attenuation factor between direct+ND and coronagraphic images
                flux_norm_dir = stroke_min.capture_flux_attenuation_data(wavelengths=self.wavelengths,
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
                self.broadband_images = []  # broadband images are however just a list

                # Take starting reference images, in direct and coron, per each wavelength
                # Note, switching direct<->coron is much slower than filter wheel changes, so
                # for efficiency we should change the FPM position the minimum number of times
                for wavelength in self.wavelengths:
                    images_direct[wavelength], _ = self.take_exposure(devices, 'direct', wavelength, initial_path, flux_norm_dir[wavelength])
                    direct_maxes[wavelength] = images_direct[wavelength].max()

                for wavelength in self.wavelengths:
                    self.images_before[wavelength], _ = self.take_exposure(devices, 'coron', wavelength, initial_path)
                    self.images_before[wavelength] /= direct_maxes[wavelength]
                    self.images_after[wavelength] = self.images_before[wavelength]

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
                        #ta_controller.acquire_target(coarse_align=False)  # TODO: HICAT-713 This requires testing at low contrast levels.
                        pass
                    # else: # TODO: HICAT-713 Add this back when the above is added back.
                    # Plot position of PSF centroid on TA camera.
                    ta_controller.distance_to_target(TargetCamera.TA)

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
                        self.images_before[wavelength] = self.images_after[wavelength]

                        if self.perfect_knowledge_mode and sim:
                            self.compute_true_e_fields(E_estimateds, exposure_kwargs, initial_path, wavelength)
                        else:
                            if self.control_weights[wavelength] == 0:
                                E_estimateds[wavelength] = hcipy.Field(np.zeros(stroke_min.focal_grid.size, dtype='complex'), stroke_min.focal_grid)
                                mean_contrast_probe[wavelength] = np.mean(np.abs(E_estimateds[wavelength][self.dark_zone]) ** 2)
                                probe_examples[wavelength] = self.images_before[wavelength]
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
                                hicat.util.save_complex(f"E_estimated_unscaled_{wavelength}nm.fits", E_estimateds[wavelength], initial_path)

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
                        self.images_after[wavelength], _ = self.take_exposure(devices, 'coron', wavelength, initial_path)
                        self.images_after[wavelength] /= direct_maxes[wavelength]

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

    def show_status_plots(self,  image_before, image_after, dm1_actuators, dm2_actuators, E_estimateds):
        self.log.info(f"Producing status plots.")
        super().show_status_plots( image_before, image_after, dm1_actuators, dm2_actuators, E_estimateds)
        self.show_broadband_strokemin_plot(E_estimateds)

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

        wl0 = self.wavelengths[0]
        wavelengths = sorted(self.wavelengths)  # because self.wavelengths has center wavelength first
        wl_sort = np.argsort(self.wavelengths)

        # define some quantities for use in labeling plots
        iteration = len(self.mean_contrasts_pairwise)
        gamma = self.adjust_gamma(iteration) if self.auto_adjust_gamma else self.gamma
        contrast_yaxis_min = min(10**(np.floor(np.log10(np.min(self.mean_contrasts_image)))-1), 1e-8)
        control_zone = np.abs(E_estimateds[wl0]) != 0

        fig, axes = plt.subplots(figsize=(20, 13), nrows=len(self.wavelengths)+1, ncols=5,
                                 gridspec_kw={'right': 0.97, 'left':0.07,
                                              'top': 0.93, 'bottom': 0.10,
                                              'wspace': 0.25, 'hspace': 0.25,
                                              'width_ratios': [1,1,1,1,1.1]})

        fig.suptitle("Broadband Multiwavelength Diagnostics", fontsize=18, weight='bold')

        def _show_one_contrast_image(field, ax, mask=False, title=None, image_crop=17):
            """ Convenience function for image display"""

            # Log plots; avoid floating underflow or divide by zero
            log_image = np.log10(field.clip(min=1e-20))
            if mask:
                tmp = log_image.copy()
                tmp[self.dark_zone==False] = -8
            else:
                tmp = log_image
            im = hcipy.imshow_field(tmp, vmin=-8, vmax=-4, cmap='inferno', ax=ax)
            hicat.plotting.image_axis_setup(ax, im, title=title, image_crop=image_crop)
            return im

        # Iterate over wavelength and plot: Estimated E field, Estimated I field, observed I field before, observed I field after, estimated incoherent

        for iwl, wl in enumerate(wavelengths):

            # Compute quantities to be used in plots
            i_estimated = np.abs(E_estimateds[wl])**2
            est_incoherent = np.abs(self.images_before[wl]-i_estimated)
            contrast_to_inc_bg_ratio = float(np.mean(self.images_before[wl][self.dark_zone]) / np.mean(est_incoherent[self.dark_zone]))

            # 0. Label with wavelength
            axmeany = axes[iwl+1, 0].get_position().intervaly.mean()
            fig.text(0.01, axmeany, f"{int(wl)} nm", weight='bold', fontsize='large', color='navy')

            # 1. Plot estimated E field
            im = hcipy.imshow_field(E_estimateds[wl], ax=axes[iwl+1,0])
            hicat.plotting.image_axis_setup(axes[iwl+1,0], im, title = f"Estimated $E$ field: {int(wl)} nm", colorbar=False)
            # 2. Plot estimated I from E
            _show_one_contrast_image(i_estimated, mask=True, title=f"Estimated $I$ (from $E$): {int(wl)} nm", ax=axes[iwl+1,1])
            axes[iwl+1, 1].text(-15, -15, "$E$ scaled by {:.3f}".format(self.e_field_scale_factors[wl][-1]), color='lightblue',
                    fontsize='x-small')
            # 3. Plot observed I field before
            #    mask the before image to just show the dark zone
            _show_one_contrast_image(self.images_before[wl], mask=True, title=f"$I$ before iteration {iteration} (masked)", ax=axes[iwl+1,2])

            # 4. Plot estimated incoherent background (unmodulated light)
            # Estimated electric field, and residual
            im = _show_one_contrast_image(est_incoherent, mask=False, ax=axes[iwl+1,3])
            hicat.plotting.image_axis_setup(axes[iwl+1,3], im, title="Estimated Incoherent Background", control_zone=control_zone)
            axes[iwl+1,3].text(-15, -15, "Contrast/(backgrd estimate): {:.3f}".format(contrast_to_inc_bg_ratio), color='white',
                    fontsize='x-small', fontweight='black')

            # 4. Plot observed I field after, full frame
            _show_one_contrast_image(self.images_after[wl], mask=False, title=f"$I$ after iteration {iteration} (full frame)", ax=axes[iwl+1,4], image_crop=None)


        # Contrast plot: Contrast vs wavelength
        ax = axes[0,0]

        monochromatic_contrasts = np.asarray([self.images_after[wl][self.dark_zone].mean() for wl in self.wavelengths])
        ax.semilogy(wavelengths, monochromatic_contrasts[wl_sort], marker='o', color='C0')
        ax.plot(np.mean(self.wavelengths), self.mean_contrasts_image[-1], marker='s', color='black')
        ax.set_xlim(600, 680)
        ax.set_xlabel("Wavelength [nm]")
        ax.set_ylabel("Contrast")
        for i, prev_contrasts in enumerate(reversed(self._bb_plot_history)):
            ax.plot(wavelengths, prev_contrasts[wl_sort], alpha=0.8**(i+1), marker='+', color='C0')
        self._bb_plot_history.append(monochromatic_contrasts)
        ax.set_title("Contrast vs Wavelength")


        # Contrast plot: contrast vs iteration
        ax = axes[0,1]
        ax.plot(self.mean_contrasts_image, 'o-', c='blue', label='Measured from image')
        ax.plot(self.mean_contrasts_pairwise, 'o:', c='green', label='Measured from pairwise')
        ax.plot(self.mean_contrasts_probe, 'o:', c='orange', label='In probe image')

        if gamma is not None:
            ax.plot(iteration, self.mean_contrasts_image[-2]*gamma, '*', markersize=10, c='red', label='Control target contrast (from $\gamma$)')

        ax.plot(np.arange(iteration)+1, self.predicted_contrasts, '*--', linewidth=1,  c='purple', label='Predicted new contrast')
        ax.set_yscale('log')
        ax.set_title("Contrast vs Iteration")
        ax.set_xlabel("Iteration")
        ax.grid(True, alpha=0.1)
        ax.legend(loc='upper right', fontsize='x-small')

        # first two plots should have identical y axis scales
        axes[0,0].set_ylim(axes[0,1].get_ylim())

        # Contrast plot: radial contrast profiles
        ax = axes[0,2]
        r_bb, p_bb, std_bb, n_bb = hcipy.metrics.radial_profile(self.broadband_images[-2], bin_size=0.25)
        r_ba, p_ba, std_ba, n_ba = hcipy.metrics.radial_profile(self.broadband_images[-1], bin_size=0.25)
        r_probe, p_probe, std_probe, n_probe = hcipy.metrics.radial_profile(self.probe_example, bin_size=0.25)
        ax.semilogy(r_bb, p_bb, color='black', alpha=0.5, label='Broadband, before', zorder=10)
        ax.semilogy(r_ba, p_ba, color='black', alpha=1, label='Broadband, after', zorder=10)
        ax.semilogy(r_probe, p_probe,  label='probe', color='orange', ls='--', zorder=3)

        colors_vs_nwavelengths = {1: ['darkmagenta'],
                                  2: ['royalblue', 'darkmagenta'],
                                  3: ['royalblue', 'darkmagenta', 'firebrick'],
                                  5: ['royalblue', 'indigo', 'darkmagenta', 'mediumvioletred', 'firebrick']}
        colors = colors_vs_nwavelengths[len(wavelengths)]
        for iwl, wl in enumerate(wavelengths):
            r2, p2, std2, n2 = hcipy.metrics.radial_profile(self.images_after[wl], bin_size=0.25)
            ax.semilogy(r2, p2, color=colors[iwl], alpha=0.8, label=f'{int(wl)} nm, after', zorder=9)
        ax.set_xlim(0, 20)
        ax.set_ylim(contrast_yaxis_min, 1e-3)
        ax.legend(loc='upper right', fontsize='x-small', framealpha=1.0)
        ax.grid(True, alpha=0.1)
        try:
            ax.axvline(self.dz_rin, color='C2', ls='--', alpha=0.3)
            ax.axvline(self.dz_rout, color='C2', ls='--', alpha=0.3)
        except Exception:
            pass # gracefully ignore older probe files that don't have these headers
        ax.set_xlabel("Separation ($\lambda/D_{LS}$)")
        ax.set_title('Contrast vs radius')

        # Plot additional quantities vs iteration
        ax = axes[0,3]
        ax.plot(self.e_field_scale_factors[wl0], label='$E$ field scale factor', marker='o', color='lightblue')
        ax.set_ylim(0, 1.5*np.max(self.e_field_scale_factors[wl0]))
        ax.legend(loc='upper left', fontsize='x-small', framealpha=1.0)
        ax.set_xlabel("Iteration")
        ax.set_title("Additional diagnostics")

        ax2 = ax.twinx()  # second Y axis for RHS
        ax2.semilogy(self.estimated_incoherent_backgrounds, 'o-', color='gray', label='Est. Incoherent background')
        ax2.semilogy(np.arange(iteration)+1, np.abs(self.predicted_contrast_deltas), color='purple', marker='*', label='Predicted contrast deltas')
        ax2.semilogy(np.arange(iteration)+1, np.abs(self.measured_contrast_deltas), color='C0', marker='*', label='Measured contrast deltas')
        ax2.set_ylim(contrast_yaxis_min, 1e-3)
        ax2.legend(loc='lower right', fontsize='x-small', framealpha=0.5)

        _show_one_contrast_image(self.broadband_images[-1], mask=False, title=f"$I$ after iteration {iteration}, broadband",
                                 ax=axes[0, 4], image_crop=None)

        # Aesthetic tweaks and labeling
        for ax in axes.ravel():
            ax.xaxis.label.set_size('x-small')
            ax.tick_params(axis='both', which='major', labelsize='x-small')
            ax.tick_params(axis='both', which='minor', labelsize='xx-small')

        labely = 0.04
        plt.text(0.03, labely, "Contrast image: {:.3e} pairwise: {:.3e}\nDark zone from {} - {} $\lambda/D_{{LS}}$\nProbes: {}, amplitude {} nm".format(
            float(self.mean_contrasts_image[-1]), float(self.mean_contrasts_pairwise[-1]), self.dz_rin, self.dz_rout, len(self.probes), self.probe_amp),
                 transform=fig.transFigure,
                 color='gray', horizontalalignment='left', verticalalignment='center')

        plt.text(0.3, labely, "Coron. Exp: {} ms $\\times$ {}\nDirect Exp: {} ms $\\times$ {}\nS.M. $\gamma$: {}\t gain: {}".format(
            self.exposure_time_coron//1000, self.num_exposures, float(self.exposure_time_direct)/1000,
            self.num_exposures, gamma if gamma is not None else 'None', self.control_gain),
                 transform=fig.transFigure,
                 color='gray', horizontalalignment='left', verticalalignment='center')

        plt.text(0.5, labely, "{}\n{}\n{}".format(
                 os.path.basename(self.jacobian_filename), os.path.basename(self.probe_filename),
                 self.git_label),
                 transform=fig.transFigure,
                 color='gray', horizontalalignment='left', verticalalignment='center')

        plt.text(0.14, 0.98, datetime.datetime.now().isoformat().split('.')[0],
                 transform=fig.transFigure,
                 color='gray', horizontalalignment='right', verticalalignment='center')

        plt.text(0.24, 0.96, os.path.split(self.output_path)[-1],
                 transform=fig.transFigure,
                 color='gray', horizontalalignment='right', verticalalignment='center')

        if testbed.testbed_state.simulation:
            plt.text(0.92, 0.97, "SIMULATED DATA!", transform=fig.transFigure,
                     color='red', fontsize='large', weight='bold',
                     horizontalalignment='right')

        self.movie_writer_broadband.add_frame()

        plt.close()