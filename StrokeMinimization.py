# flake8: noqa: E402

import hicat.simulators
sim = hicat.simulators.auto_enable_sim()

import numpy as np
import os
import matplotlib.pyplot as plt
from astropy.io import fits
import functools
import glob
import datetime
from shutil import copyfile
import hcipy

import hicat.plotting
import hicat.plotting.animation
from hicat.experiments.Experiment import Experiment
from hicat.hardware import testbed
import hicat.util
from hicat.wfc_algorithms import stroke_min


class StrokeMinimization(Experiment):
    """ Stroke Minimization experiment class

    :param jacobian_filename: Jacobian matrix file name path
    :param probe_filename: Observation matrix file name path
    :param num_iterations:  Number of iterations to run before convergence
    :param num_exposures:  Number of exposures for the camera
    :param exposure_time_coron:  Exposure time in the coronagraphic mode (microsec)
    :param exposure_time_direct:  Exposure time in the direct mode (microsec)
    :param use_dm2: Bool to use DM2 for control (2 sided DZ) or not (1 sided)
    :param gamma: Scaling parameter for Stroke Minimization control aggressiveness
    :param auto_adjust_gamma: Start gamma at 0.5 for first 10 iterations, then
           step towards the provided gamma value? Intended for rapidly digging the
           initial part of a dark hole more aggressively. Note, it may not work well to
           use this at the same time as resume=True, because aggressive gamma is
           not stable if you are already at fairly deep contrast.
    :param control_gain: optional gain for the control loop
    :param autoscale_e_field:  [Hack Mode] Brute force autoscaling of the E-field to match intensity at each iteration
    :param direct_every:  defines how often a direct image is taken for the contrast calibration
    :param resume: bool, try to find and reuse DM settings from prior dark zone.
    :param dm_command_dir_to_restore: string, path to the directory where the dm_commands are located for restoring dm
           settings.
    :param dm_calibration_fudge: coefficient on DM2 for rescaling. probably temporary.
    :param mu_start: starting value for Lagrange multiplier line search
    :param suffix: Name of simulation when generating output directory
    """

    name = "Stroke Minimization"

    def __init__(self, jacobian_filename, probe_filename, num_iterations,
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
                 suffix = 'stroke_minimization'):
        super(StrokeMinimization, self).__init__(suffix=suffix)

        self.jacobian_filename = jacobian_filename
        self.probe_filename = probe_filename
        try:
            self.log.info('Reading Jacobian from {}...'.format(jacobian_filename))
            self.jacobian = hcipy.read_fits(jacobian_filename)
        except Exception:
            raise RuntimeError("Can't read Jacobian from {}.".format(jacobian_filename))

        # Read dark zone geometry, probes, and obs matrix all in from extensions in the same file
        with fits.open(probe_filename) as probe_info:

            self.log.info("Loading Dark Zone geometry from {}".format(probe_filename))
            self.dark_zone = hcipy.Field(np.asarray(probe_info['DARK_ZONE'].data, bool).ravel(), stroke_min.focal_grid)
            self.dark_zone_probe = hcipy.Field(np.asarray(probe_info['DARK_ZONE_PROBE'].data, bool).ravel(), stroke_min.focal_grid)

            self.log.info("Loading probe DM shapes from {}".format(probe_filename))
            self.probes = probe_info['PROBES'].data

            self.log.info("Loading observation matrix from {}".format(probe_filename))
            self.H_inv = probe_info['OBS_MATRIX'].data

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
            self.jacobian = self.jacobian[:stroke_min.num_actuators, :]

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
        self.e_field_scale_factors = []
        self.git_label = hicat.util.git_description()

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
        self.mean_contrasts_image = []
        self.mean_contrasts_pairwise = []
        self.mean_contrasts_probe = []
        self.predicted_contrasts = []
        self.predicted_contrast_deltas = []
        self.measured_contrast_deltas = []
        self.estimated_incoherent_backgrounds = []

        # Bind exposure time to exposure functions to ensure consistency throughout experiment
        self.take_coron_exposure = functools.partial(stroke_min.take_exposure_hicat,
                                                     exposure_time=self.exposure_time_coron,
                                                     exposure_type='coron')

        self.take_direct_exposure = functools.partial(stroke_min.take_exposure_hicat,
                                                      exposure_time=self.exposure_time_direct,
                                                      exposure_type='direct')

        # Initialize output path and logging
        self.output_path = hicat.util.create_data_path(suffix=self.suffix)
        hicat.util.setup_hicat_logging(self.output_path, self.suffix)
        print("LOGGING: "+self.output_path+"  "+self.suffix)

        # Before doing anything more interesting, save a copy of the probes to disk
        self.save_probes()

    def __del__(self):
        try:
            if hasattr(self,'movie_writer'):
                self.movie_writer.close()
        except Exception:
            pass

    def collect_metrics(self, devices):
        self.timestamp.append(datetime.datetime.now().isoformat().split('.')[0])
        try:
            temp, humidity = devices['temp_sensor'].get_temp_humidity()
        except Exception:
            temp = None
            humidity = None
            self.log.exception("Failed to get temp & humidity data")
        finally:
            self.temp.append(temp)
            self.humidity.append(humidity)

        filename = os.path.join(self.output_path, "metrics.csv")
        #write header
        if not os.path.exists(filename):
            with open(filename, mode='a') as metric_file:
                metric_file.write("time stamp, temp (C), humidity (%), mean image contrast\n")

        with open(filename, mode='a') as metric_file:
            metric_file.write(f"{self.timestamp[-1]}, {self.temp[-1]}, {self.humidity[-1]}, {self.mean_contrasts_image[-1]}\n")


    def get_initial_dm_commands(self):
        """ Initialize the DM actuator commands.  This is called in __init__()."""
        if self.resume:
            dm1_actuators, dm2_actuators = self.restore_last_strokemin_dm_shapes(self.dm_command_dir_to_restore)
        else:
            # Check if Jacobian includes information on which DM state it is linearized around
            try:
                dm_settings = fits.getdata(self.jacobian_filename, extname='DM_SETTINGS' )
                dm1_actuators = dm_settings[0]
                dm2_actuators = dm_settings[1]
            except KeyError:
                # no DM settings saved, therefore start with flat DMs
                dm1_actuators = np.zeros(stroke_min.num_actuators)
                dm2_actuators = np.zeros(stroke_min.num_actuators)

        return dm1_actuators, dm2_actuators

    def experiment(self):
        # Initialize the testbed devices once, to reduce overhead of opening/intializing
        # each one for each exposure.
        with testbed.laser_source() as laser, \
                testbed.dm_controller() as dm, \
                testbed.motor_controller() as motor_controller, \
                testbed.beam_dump() as beam_dump, \
                testbed.imaging_camera() as cam, \
                testbed.pupil_camera() as pupilcam, \
                testbed.temp_sensor(ID=2) as temp_sensor, \
                testbed.color_wheel() as color_wheel:
            devices = {'laser': laser,
                       'dm': dm,
                       'motor_controller': motor_controller,
                       'beam_dump': beam_dump,
                       'imaging_camera': cam,
                       'pupil_camera': pupilcam,
                       'temp_sensor': temp_sensor,
                       'color_wheel': color_wheel}

            out_path = os.path.join(self.output_path, 'before')
            exposure_kwargs = {'initial_path': out_path,
                               'num_exposures': self.num_exposures}

            # Take starting reference images, in direct and coron
            image_before, _header = self.take_coron_exposure(
                self.dm1_actuators, self.dm2_actuators, devices, **exposure_kwargs)
            direct, _header = self.take_direct_exposure(
                self.dm1_actuators, self.dm2_actuators, devices, **exposure_kwargs)
            image_before /= direct.max()
            image_after = image_before

            # set up plot writing infrastructure
            self.init_strokemin_plots()

            self.mean_contrasts_image.append(np.mean(image_before[self.dark_zone]))

            self.collect_metrics(devices)

            for i in range(self.num_iterations):
                self.log.info("Pairwise sensing and stroke minimization, iteration {}".format(i))
                # Create a new output subfolder for each iteration
                exposure_kwargs['initial_path'] = os.path.join(self.output_path, 'iter{:04d}'.format(i))

                # and make a temporary function that's pre-set to write files into that folder, for
                # passing into the pairwise function
                take_exposure_func = functools.partial(self.take_coron_exposure, devices=devices,
                                                       **exposure_kwargs)

                image_before = image_after

                self.log.info('Estimating electric fields using pairwise probes...')
                E_estimated, probe_example = stroke_min.take_electric_field_pairwise(self.dm1_actuators,
                                                                                     self.dm2_actuators,
                                                                                     take_exposure_func,
                                                                                     devices,
                                                                                     self.H_inv,
                                                                                     self.probes,
                                                                                     self.dark_zone,
                                                                                     direct,
                                                                                     initial_path=exposure_kwargs['initial_path'],
                                                                                     current_contrast=self.mean_contrasts_image[-1] if i>0 else None,
                                                                                     probe_amplitude=self.probe_amp)
                hicat.util.save_complex("E_estimated_unscaled.fits", E_estimated, exposure_kwargs['initial_path'])
                self.probe_example = probe_example  # Save for use in plots

                if self.autoscale_e_field:
                    # automatically scale the estimated E field to match the prior image contrast
                    expected_contrast = self.mean_contrasts_image[-1]
                    estimated_contrast = np.mean(np.abs(E_estimated[self.dark_zone]) ** 2)
                    contrast_ratio = expected_contrast/estimated_contrast
                    self.log.info("Scaling estimated e field by {} to match image contrast ".format(np.sqrt(contrast_ratio)))
                    self.e_field_scale_factors.append(np.sqrt(contrast_ratio))
                else:
                    self.e_field_scale_factors.append(1.)

                E_estimated *= self.e_field_scale_factors[-1]

                if sim:
                    E_sim_actual, _header = stroke_min.take_electric_field_simulator(self.dm1_actuators,
                                                                                     self.dm2_actuators,
                                                                                     apply_pipeline_binning=False)  # E_actual is in sqrt(counts/sec)
                    direct_sim, _header = stroke_min.take_direct_exposure_simulator(self.dm1_actuators,
                                                                                    self.dm2_actuators)
                    E_sim_normalized = E_sim_actual / direct_sim.max()
                    hicat.util.save_complex("E_actual.fits", E_sim_normalized, exposure_kwargs['initial_path'])
                    hicat.util.save_intensity("I_actual_from_sim_cal.fits", E_sim_normalized, exposure_kwargs['initial_path'])
                    E_sim_actual, _header = stroke_min.take_electric_field_simulator(self.dm1_actuators,
                                                                                     self.dm2_actuators,
                                                                                     apply_pipeline_binning=True)  # E_actual is in sqrt(counts/sec)

                    E_sim_normalized = E_sim_actual / direct_sim.max()
                    hicat.util.save_intensity("I_actual_from_sim_bin.fits", E_sim_normalized, exposure_kwargs['initial_path'])

                # Save raw contrast from pairwise and probes, for use in plots
                self.mean_contrasts_pairwise.append(np.mean(np.abs(E_estimated[self.dark_zone]) ** 2))
                self.mean_contrasts_probe.append(np.mean(self.probe_example[self.dark_zone]))

                self.log.info('Calculating stroke min correction, iteration {}...'.format(i))

                gamma = self.adjust_gamma(i) if self.auto_adjust_gamma else self.gamma

                # Find the required DM update here
                correction, self.mu_start, predicted_contrast, predicted_contrast_drop = self.compute_correction(
                    E_estimated, gamma, devices, exposure_kwargs, direct)

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

                # Track temp and humidity. Measure as close to image acquisition as possible.
                self.collect_metrics(devices)
                self.log.info('Taking post-correction coronagraphic image and pupil image...')
                image_after, _header = self.take_coron_exposure(self.dm1_actuators, self.dm2_actuators, devices,
                                                           **exposure_kwargs)
                try:
                    self.latest_pupil_filename = stroke_min.take_pupilcam_hicat(devices, initial_path=exposure_kwargs['initial_path'])[0]
                except Exception:
                    # FIXME temporary workaround
                    self.log.warning("PUPIL CAM EXCEPTION ENCOUNTERED - IGNORING AND CONTINUING")

                self.latest_pupil_image = fits.getdata(self.latest_pupil_filename)

                if np.mod(i, self.direct_every) == 0:
                    self.log.info('Taking direct image for comparison...')
                    direct, _header = self.take_direct_exposure(self.dm1_actuators, self.dm2_actuators, devices,
                                                                **exposure_kwargs)

                image_after /= direct.max()

                # Save raw contrast from image
                self.mean_contrasts_image.append(np.mean(image_after[self.dark_zone]))

                self.measured_contrast_deltas.append(self.mean_contrasts_image[-1] - self.mean_contrasts_image[-2])
                self.log.info("===> Measured contrast drop this iteration: {}".format(self.measured_contrast_deltas[-1]))

                est_incoherent = np.abs(image_before-np.abs(E_estimated)**2)
                self.estimated_incoherent_backgrounds.append(np.mean(est_incoherent[self.dark_zone]))

                # make diagnostic plot
                self.show_strokemin_plot(image_before, image_after, self.dm1_actuators, self.dm2_actuators, E_estimated)

    def compute_correction(self, E_estimated, gamma, devices, exposure_kwargs, direct_image):
        """
        Calculate the DM actuator correction for a given field estimate and contrast decrease factor.
        """
        correction, mu_start, predicted_contrast, predicted_contrast_drop = stroke_min.stroke_minimization(
            self.jacobian, E_estimated, self.dark_zone, gamma, self.mu_start)

        return correction, mu_start, predicted_contrast, predicted_contrast_drop

    def adjust_gamma(self, iteration_number):
        """ Vary Gamma as a function of iteration number. Start aggressive, then become less so over time.

        This is a very crude version of this function and should eventually be replaced with something
        more clever.

        Start at 0.5, then approach the provided input gamma as the eventual limit.

        """
        if iteration_number < 10:
            gamma = 0.5
        elif iteration_number < 20:
            gamma = (0.5+self.gamma)/2
        else:
            gamma = self.gamma
        self.log.info("Automatic adjustment of Gamma: Stroke min iteration {} using Gamma = {}".format(iteration_number, gamma))
        return gamma

    def save_probes(self, output_path=None, save_plots=False):
        """ Save probes to disk
        """
        if output_path is None:
            output_path = os.path.join(self.output_path, 'probes')

        self.log.info('Recording probe vectors to {}'.format(output_path))
        os.makedirs(output_path, exist_ok=True)

        # TODO also save the dark_zone mask here too, and dark_zone_probe.

        for i, p in enumerate(self.probes):
            p1, p2 = stroke_min.split_command_vector(p, self.use_dm2)
            acts1 = stroke_min.dm_actuators_to_surface(p1)
            acts2 = stroke_min.dm_actuators_to_surface(p2)

            hcipy.write_fits(acts1, os.path.join(output_path, 'probe_%d_dm1.fits' % i))
            hcipy.write_fits(acts2, os.path.join(output_path, 'probe_%d_dm2.fits' % i))

            if save_plots:
                plt.figure(figsize=(14, 10))
                plt.subplot(1, 2, 1)
                vmx = np.abs(acts1).max()
                print('a')
                hcipy.imshow_field(acts1, cmap='RdBu', vmin=-vmx, vmax=vmx)
                plt.title("DM1")
                plt.colorbar()
                print('b')
                plt.subplot(1, 2, 2)
                hcipy.imshow_field(acts2, cmap='RdBu', vmin=-vmx, vmax=vmx)
                plt.title("DM2")
                print('c')
                plt.colorbar()
                plt.suptitle("Probe %d" % i)
                plt.tight_layout()

                print(i, 'end')
                plt.savefig(os.path.join(output_path, "probe_%d.png" % i))
        self.log.info('  Probe vectors saved to {}'.format(output_path))

        # Save probe images to experiment folder
        probe_pdf_src = os.path.splitext(self.probe_filename)[0] + '.pdf'
        probe_pdf_destination = os.path.join(self.output_path, 'probes', os.path.basename(probe_pdf_src))
        try:
            copyfile(probe_pdf_src, probe_pdf_destination)
        except OSError:
            self.log.warning("Failed to copy '{}' to '{}'".format(probe_pdf_src, probe_pdf_destination))


    def init_strokemin_plots(self, output_path=None):
        """ Set up the infrastructure for writing out plots
        in particular the GifWriter object and output directory
        """
        if output_path is None:
            output_path = os.path.join(self.output_path, 'stroke_min_sequence.gif')
        self.log.info("Diagnostic images will be saved to " + output_path)
        #  The hcipy.GifWriter() makes the correct dirs for us.
        self.movie_writer = hicat.plotting.animation.GifWriter(output_path, framerate=2, cleanup=False)

    def show_strokemin_plot(self, image_before, image_after, dm1_actuators, dm2_actuators, E_estimated):
        """ Make a nice diagnostic plot after each iteration of stroke minimization
        and save it to the movie in progress.

        Note, only call this after calling init_strokemin_plots.
        """

        # Show results
        # Log plots; avoid floating underflow or divide by zero
        log_img_before = np.log10(image_before)
        log_img_before[image_before <= 0] = -20
        log_img_after = np.log10(image_after)
        log_img_after[image_after <= 0] = -20

        log_i_estimated = np.log10(np.clip(np.abs(E_estimated)**2, a_min=1e-12, a_max=1.0))

        est_incoherent = np.abs(image_before-np.abs(E_estimated)**2)
        log_est_incoherent = np.log10(est_incoherent)

        contrast_to_inc_bg_ratio = float(np.mean(image_before[self.dark_zone]) / np.mean(est_incoherent[self.dark_zone]))

        # define some other quantities for use in labeling plots
        iteration = len(self.mean_contrasts_pairwise)
        gamma = self.adjust_gamma(iteration) if self.auto_adjust_gamma else self.gamma
        contrast_yaxis_min = min(10**(np.floor(np.log10(np.min(self.mean_contrasts_image)))-1), 1e-8)
        control_zone = np.abs(E_estimated) != 0

        fig, axes = plt.subplots(figsize=(20, 13), nrows=3, ncols=5,
                                 gridspec_kw={'right': 0.95, 'left':0.03,
                                              'top': 0.93, 'bottom': 0.10,
                                              'wspace': 0.25, 'hspace': 0.25,
                                              'width_ratios': [1,1,1,1,1.1]})

        #Estimation and Sensing
        ax = axes[0,0]
        im = hcipy.imshow_field(E_estimated, ax=ax)
        hicat.plotting.image_axis_setup(ax, im, title = "Estimated $E$ field", colorbar=False)

        ax = axes[1,0]
        im = hcipy.imshow_field(log_i_estimated, vmin=-8, vmax=-4, cmap='inferno', ax=ax)
        hicat.plotting.image_axis_setup(ax, im, title="Estimated $I$ (from $E$)")
        ax.text(-15, -15, "$E$ scaled by {:.3f}".format(self.e_field_scale_factors[-1]), color='lightblue',
                fontsize='x-small')

        # Display images, before and after
        # mask the before image to just show the dark zone
        ax = axes[2,0]
        log_img_before_masked = log_img_before.copy()
        log_img_before_masked[self.dark_zone == False] = -8
        im = hcipy.imshow_field(log_img_before_masked, vmin=-8, vmax=-4, cmap='inferno', ax=ax)
        hicat.plotting.image_axis_setup(ax, im, title="Image before iteration {} (Masked)".format(iteration), control_zone=control_zone)

        ax = axes[0,4]
        im = hcipy.imshow_field(log_img_after, vmin=-8, vmax=-4, cmap='inferno', ax=ax)
        hicat.plotting.image_axis_setup(ax, im, title="Image after iteration {}".format(iteration), control_zone=control_zone)

        # Contrast plot: contrast vs iteration
        ax = axes[0,1]
        ax.plot(self.mean_contrasts_image, 'o-', c='blue', label='Measured from image')
        ax.plot(self.mean_contrasts_pairwise, 'o:', c='green', label='Measured from pairwise')
        ax.plot(self.mean_contrasts_probe, 'o:', c='orange', label='In probe image')

        if gamma is not None:
            ax.plot(iteration, self.mean_contrasts_image[-2]*gamma, '*', markersize=10, c='red', label='Control target contrast')

        ax.plot(np.arange(iteration)+1, self.predicted_contrasts, '*--', linewidth=1,  c='purple', label='Predicted new contrast')
        ax.set_yscale('log')
        ax.set_title("Contrast vs Iteration")
        ax.set_xlabel("Iteration")
        ax.grid(True, alpha=0.1)
        ax.legend(loc='upper right', fontsize='x-small')

        # Contrast plot: radial contrast profiles
        ax = axes[0,2]
        r, p, std, n = hcipy.metrics.radial_profile(image_after, bin_size=0.25)
        r2, p2, std2, n2 = hcipy.metrics.radial_profile(image_before, bin_size=0.25)
        r_probe, p_probe, std_probe, n_probe = hcipy.metrics.radial_profile(self.probe_example, bin_size=0.25)
        ax.semilogy(r2, p2, color='C0', alpha=0.4, label='before', zorder=10)
        ax.semilogy(r, p, color='C0', label='after', zorder=9)
        ax.semilogy(r_probe, p_probe,  label='probe', color='orange', ls='--', zorder=3)
        ax.set_xlim(0, 20)
        ax.set_ylim(contrast_yaxis_min, 1e-3)
        ax.legend(loc='upper left', fontsize='x-small', framealpha=1.0)
        ax.grid(True, alpha=0.1)
        try:
            ax.axvline(self.dz_rin, color='C2', ls='--', alpha=0.3)
            ax.axvline(self.dz_rout, color='C2', ls='--', alpha=0.3)
        except Exception:
            pass # gracefully ignore older probe files that don't have these headers
        ax.set_xlabel("Separation ($\lambda/D_{apod}$)")
        ax.set_title('Contrast vs radius')

        # Plot additional quantities vs iteration
        ax = axes[0,3]
        ax.plot(self.e_field_scale_factors, label='$E$ field scale factor', marker='o', color='lightblue')
        ax.set_ylim(0, 1.5*np.max(self.e_field_scale_factors))
        ax.legend(loc='upper left', fontsize='x-small', framealpha=1.0)
        ax.set_xlabel("Iteration")
        ax.set_title("Additional diagnostics")

        ax2 = ax.twinx()  # second Y axis for RHS
        ax2.semilogy(self.estimated_incoherent_backgrounds, 'o-', color='gray', label='Est. Incoherent background')
        ax2.semilogy(np.arange(iteration)+1, np.abs(self.predicted_contrast_deltas), color='purple', marker='*', label='Predicted contrast deltas')
        ax2.semilogy(np.arange(iteration)+1, np.abs(self.measured_contrast_deltas), color='C0', marker='*', label='Measured contrast deltas')
        ax2.set_ylim(contrast_yaxis_min, 1e-3)
        ax2.legend(loc='lower right', fontsize='x-small', framealpha=0.5)

        # Display DMs, and changes. Note, the correction is subtracted off so the change sign is negative.
        dm1_surf = stroke_min.dm_actuators_to_surface(dm1_actuators)
        if self.use_dm2:
            dm1_delta = -stroke_min.dm_actuators_to_surface(self.correction[:stroke_min.num_actuators])
            dm1_delta_2 = -stroke_min.dm_actuators_to_surface((self.correction+self.prior_correction)[:stroke_min.num_actuators])/2

            dm2_surf = stroke_min.dm_actuators_to_surface(dm2_actuators)
            dm2_delta = -stroke_min.dm_actuators_to_surface(self.correction[stroke_min.num_actuators:])
            dm2_delta_2 = -stroke_min.dm_actuators_to_surface((self.correction+self.prior_correction)[stroke_min.num_actuators:])/2

            vmax = max([np.abs(dm1_surf).max(), np.abs(dm2_surf).max()])
            dvmax = max([np.abs(dm1_delta).max(), np.abs(dm2_delta).max()])

        else:
            dm1_delta = -stroke_min.dm_actuators_to_surface(self.correction)
            dm1_delta_2 = -stroke_min.dm_actuators_to_surface((self.correction+self.prior_correction))/2

            vmax = max([np.abs(dm1_surf).max(), np.abs(dm1_surf).max()])
            dvmax = max([np.abs(dm1_delta).max(), np.abs(dm1_delta).max()])

        # DM1 plots
        hicat.plotting.dm_surface_display(axes[1,1], dm1_surf, vmax=vmax, title='DM1 surface')
        hicat.plotting.dm_surface_display(axes[1,2], dm1_delta, vmax=dvmax, title='DM1 change this iteration')
        hicat.plotting.dm_surface_display(axes[1,3], dm1_delta_2, vmax=dvmax, title='DM1 average change last 2 iters')

        # DM2 plots
        if self.use_dm2:
            hicat.plotting.dm_surface_display(axes[2,1], dm2_surf, vmax=vmax, title='DM2 surface')
            hicat.plotting.dm_surface_display(axes[2,2], dm2_delta, vmax=dvmax, title='DM2 change this iteration')
            hicat.plotting.dm_surface_display(axes[2,3], dm2_delta_2, vmax=dvmax, title='DM2 average change last 2 iters')

        # Pupil image
        ax = axes[1,4]
        ax.imshow(self.latest_pupil_image)
        ax.set_title("Pupil image")
        ax.yaxis.set_visible(False)
        ax.xaxis.set_visible(False)

        # Estimated electric field, and residual
        ax = axes[2,4]
        im = hcipy.imshow_field(log_est_incoherent, vmin=-8, vmax=-4, cmap='inferno', ax=ax)
        hicat.plotting.image_axis_setup(ax, im, title="Estimated Incoherent Background", control_zone=control_zone)
        ax.text(-15, -15, "Contrast/(backgrd estimate): {:.3f}".format(contrast_to_inc_bg_ratio), color='k',
                fontsize='x-small', fontweight='black')

        # Aesthetic tweaks and labeling
        for ax in axes.ravel():
            ax.xaxis.label.set_size('x-small')
            ax.tick_params(axis='both', which='major', labelsize='x-small')
            ax.tick_params(axis='both', which='minor', labelsize='xx-small')

        labely = 0.04
        plt.text(0.03, labely, "Contrast image: {:.3e} pairwise: {:.3e}\nDark zone from {} - {} $\lambda/D$\nProbes: {}, amplitude {} nm".format(
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

        self.movie_writer.add_frame()

        plt.close()

    def restore_last_strokemin_dm_shapes(self, dm_command_dir_to_restore=None):
        """ Find most recent prior DM shapes and re-use them, if possible.

        Method: Look at all available stroke min directories.
        Sort these in reverse to find the most recent deep stroke min run.
        Ignore any that have fewer than ten iterations (assume these were for script
        debugging, or are just not that dark, etc.).
        Get the DM settings from the penultimate iteration folder (since the last
        iteration probably did not complete.)

        """
        if dm_command_dir_to_restore is None:
            min_iterations_to_resume = 10

            self.log.info("Resuming DM settings from prior dark zone.")
            initial_path = hicat.util.map_data_path()
            pattern = os.path.join(initial_path, '*_' + self.suffix)
            self.log.info("Looking for " + pattern)
            stroke_min_runs = glob.glob(pattern)
            stroke_min_runs.sort(reverse=True)

            if len(stroke_min_runs) == 0:
                self.log.info("Could not find any stroke min directories to resume from.")
                return np.zeros(stroke_min.num_actuators), np.zeros(stroke_min.num_actuators)

            for prior_dir in stroke_min_runs:
                self.log.info("Checking dir: " + prior_dir)
                iter_dirs = glob.glob(os.path.join(prior_dir, 'iter*'))
                if len(iter_dirs) < min_iterations_to_resume:
                    self.log.info(
                        "  That dir has < {} iterations, so we are skipping it.".format(min_iterations_to_resume))
                    continue

                iter_dirs.sort()
                # Get the penultimate iteration; the last one may not have completed yet.
                iter_to_restore = iter_dirs[-2]
                dir_to_restore = glob.glob(os.path.join(iter_to_restore, '*_coron', 'coron', 'dm_command'))[0]
                self.log.info("Retrieving DM settings from " + dir_to_restore)
                break

                self.log.info("Could not find any stroke min directories with > {} iterations.".format(min_iterations_to_resume))
                return np.zeros(num_actuators), np.zeros(num_actuators)
        else:
            self.log.info("Resuming DM setting from directory: " + dm_command_dir_to_restore)
            dir_to_restore = dm_command_dir_to_restore
            # Load DM surfaces from the so-called noflat files, i.e. the requested surface
            # displacements prior to adding in the DM flat map calibration

        surfaces = []
        for dmnum in [1, 2]:
            actuators_2d = fits.getdata(os.path.join(dir_to_restore, 'dm{}_command_2d_noflat.fits'.format(dmnum)))
            actuators_1d = actuators_2d.ravel()[stroke_min.dm_mask]
            actuators_1d *= 1e9  # convert from meters to nanometers # FIXME this is because of historical discrepancies, need to unify everything at some point
            surfaces.append(actuators_1d)
        return surfaces

    def sanity_check(self, correction):
        """ Perform simple test for basic plausibility of results """

        peak_to_valley = np.ptp(correction)
        max_corr = 200 # FIXME : this should be a config read
        if peak_to_valley > max_corr:
            raise RuntimeError('Implausibly large correction! Requested DM stroke of {} nm PTV which is very large. '
                               'Something is likely wrong with the Jacobian, or other algorithm settings. '
                               'Terminating execution.'.format(max_corr))
