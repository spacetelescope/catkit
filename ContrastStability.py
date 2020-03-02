# flake8: noqa: E402

import hicat.simulators
sim = hicat.simulators.auto_enable_sim()

import os
import functools
import datetime
import time
import numpy as np
from astropy.io import fits
import hcipy
import matplotlib.pyplot as plt

from hicat.experiments.Experiment import Experiment
from hicat.hardware import testbed
import hicat.plotting.animation
import hicat.plotting
from hicat import util
from hicat.experiments.modules import stroke_min

# Redefine take image functions like in run_stroke_min
exposure_time_coron = 100000
exposure_time_direct = 100

take_coron_exposure = functools.partial(stroke_min.take_exposure_hicat, exposure_time=exposure_time_coron,
                                        exposure_type='coron')
take_direct_exposure = functools.partial(stroke_min.take_exposure_hicat, exposure_time=exposure_time_direct,
                                         exposure_type='direct')


class ContrastStability(Experiment):

    name = "Contrast Stability Test"

    def __init__(self, dm_command_path, dh_filename, iterations=50, num_exposures=10, sleep=1):
        """
        Load DM maps on DM1 and DM2, hold them, and measure contrast with a user-specified cadence.

        :param dm_command_path: string, path to DM commands
        :param dh_filename: string, observation matrix
        :param iterations: int, number of consecutive measurements to take
        :param num_exposures: int, number of exposures per measurement
        :param sleep: float, time for the script to wait between measurements ON TOP of the image acquisition and processing
        """
        suffix = "contrast_stability"
        super().__init__(suffix=suffix, output_path=util.create_data_path(suffix=suffix))
        self.dh_filename = dh_filename
        self.iter = iterations
        self.num_exposures = num_exposures
        self.mean_contrasts_image = []
        self.sleep = sleep

        # Metrics
        self.timestamp = []
        self.temp = []
        self.humidity = []

        # Read dark zone
        with fits.open(dh_filename) as probe_info:

            self.log.info("Loading Dark Zone geometry from {}".format(dh_filename))
            self.dark_zone = hcipy.Field(np.asarray(probe_info['DARK_ZONE'].data, bool).ravel(), stroke_min.focal_grid)

        # Load DM shape you want to use for test
        dm1_start = fits.getdata(os.path.join(dm_command_path, 'dm1_command_2d_noflat.fits')).ravel()
        dm2_start = fits.getdata(os.path.join(dm_command_path, 'dm2_command_2d_noflat.fits')).ravel()
        self.dm1_hold = dm1_start[stroke_min.dm_mask] * 1e9   # The file saves the DM maps in meters, while the
        self.dm2_hold = dm2_start[stroke_min.dm_mask] * 1e9   # take exposure function needs them in nanometers.

    def collect_metrics(self, devices):
        """
        Totally hijacked from run_strokemin.py, but that one over there didn't have a docstring.

        Measure temperature and humidity and save those values with most recent image contrast.
        :param devices: dict of HiCAT devices
        :return:
        """
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

    def experiment(self):

        util.setup_hicat_logging(self.output_path, self.suffix)
        print("LOGGING: " + self.output_path + "  " + self.suffix)
        self.movie_writer = hicat.plotting.animation.GifWriter(os.path.join(self.output_path, 'contrast_sequence.gif'),
                                                               framerate=2, cleanup=False)

        with testbed.laser_source() as laser, \
                testbed.dm_controller() as dm, \
                testbed.motor_controller() as motor_controller, \
                testbed.beam_dump() as beam_dump, \
                testbed.imaging_camera() as cam, \
                testbed.temp_sensor(ID=2) as temp_sensor:
            devices = {'laser': laser,
                       'dm': dm,
                       'motor_controller': motor_controller,
                       'beam_dump': beam_dump,
                       'imaging_camera': cam,
                       'temp_sensor': temp_sensor}

            # Take direct exposure for normalization
            direct, _header = take_direct_exposure(np.zeros(stroke_min.num_actuators),
                                                   np.zeros(stroke_min.num_actuators),
                                                   devices,
                                                   initial_path=self.output_path,
                                                   num_exposures=self.num_exposures)

            for i in range(self.iter):

                coron, _header = take_coron_exposure(self.dm1_hold, self.dm2_hold,
                                                     devices, num_exposures=self.num_exposures,
                                                     initial_path=self.output_path)
                coron /= direct.max()
                self.mean_contrasts_image.append(np.mean(coron[self.dark_zone]))

                # Track temp and humidity. Measure as close to image acquisition as possible. But after measuring contrast.
                self.collect_metrics(devices)

                # Plot
                self.show_contrast_stability_plot(coron, self.timestamp, self.mean_contrasts_image, self.temp, self.humidity, mw=self.movie_writer)

                # Delay next iteration to control data cadence. This is on top of the full processing loop.
                time.sleep(self.sleep)


    def show_contrast_stability_plot(self, image, timestamp, contrast_list, temp_list, hum_list, mw=None):

        log_img = np.log10(image)
        log_img[image <= 0] = -20
        iteration = len(contrast_list)
        fig, axes = plt.subplots(figsize=(20, 13), nrows=2, ncols=2)

        # Image
        ax = axes[0, 1]
        im = hcipy.imshow_field(log_img, vmin=-8, vmax=-4, cmap='inferno', ax=ax)
        hicat.plotting.image_axis_setup(ax, im, title="Image after iteration {}".format(iteration))

        # Contrast plot: contrast vs time stamp
        # plus humidity and temperature
        ax = axes[0, 0]
        ax.plot(timestamp, contrast_list, 'o-', c='blue', label='Mean contrast')
        ax2 = ax.twinx()
        ax2.plot(timestamp, temp_list, 'o-', c='red', label='Temperature (C)')
        ax2.plot(timestamp, hum_list, 'o-', c='green', label='Humidity (%)')
        ax.set_yscale('log')
        ax2.set_ylim(5, 30)
        ax.set_title("Contrast stability test")
        ax.set_xlabel("Time")
        ax.grid(True, alpha=0.1)
        ax.legend(loc='upper left', fontsize='x-small')
        ax2.legend(loc='upper right', fontsize='x-small')

        # The two DMs
        dm1_surf = stroke_min.dm_actuators_to_surface(self.dm1_hold)
        dm2_surf = stroke_min.dm_actuators_to_surface(self.dm2_hold)
        vmax = max([np.abs(dm1_surf).max(), np.abs(dm2_surf).max()])

        hicat.plotting.dm_surface_display(axes[1, 0], dm1_surf, vmax=vmax, title='DM1 surface')
        hicat.plotting.dm_surface_display(axes[1, 1], dm2_surf, vmax=vmax, title='DM2 surface')

        # Time stamp
        plt.text(0.95, 0.05, datetime.datetime.now().isoformat().split('.')[0],
                 transform=fig.transFigure,
                 color='gray', horizontalalignment='right', verticalalignment='center')

        mw.add_frame()
        plt.close()
