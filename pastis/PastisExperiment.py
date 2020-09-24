import hicat.simulators
import glob
import os
from astropy.io import fits
import hcipy
import numpy as np

from hicat.config import CONFIG_INI
from hicat.experiments.Experiment import HicatExperiment
from hicat.experiments.modules import pastis_functions
from hicat.hardware import testbed_state
from hicat.hardware.testbed import move_filter
from hicat.wfc_algorithms import stroke_min

import pastis.util


class PastisExperiment(HicatExperiment):
    """
    Top-level PASTIS experiment class, inheriting from HicatExperiment.

    This adds a method to do the flux normalization, and a method that measures the reference PSF, as well as the
    unaberrated coronagraph PSF that has a DH solution applied on the DMs.
    """

    name = 'PASTIS Experiment'

    def __init__(self, probe_filename, dm_map_path, color_filter, nd_direct, nd_coron,
                 num_exposures, exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                 align_lyot_stop=True, run_ta=True):
        """
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
        super().__init__()
        self.probe_filename = probe_filename  # needed for DH geometry only
        self.dm_map_path = dm_map_path  # will need to load these DM maps to get to low contrast (take from good PW+SM run)
        self.align_lyot_stop = align_lyot_stop
        self.run_ta = run_ta

        self.color_filter = color_filter
        self.nd_direct = nd_direct
        self.nd_coron = nd_coron
        self.num_exposures = num_exposures
        self.exposure_time_coron = exposure_time_coron
        self.exposure_time_direct = exposure_time_direct
        self.auto_expose = auto_expose
        self.file_mode = file_mode
        self.raw_skip = raw_skip

        # General telescope parameters
        self.nb_seg = 37
        self.seglist = pastis.util.get_segment_list('HiCAT')
        self.wvln = 640    # nm
        self.log.info(f'Number of segments: {self.nb_seg}')
        self.log.info(f'Segment list: {self.seglist}')

        # Read DM commands, treated as part of the coronagraph
        self.dm1_actuators, self.dm2_actuators = pastis_functions.read_dm_commands(self.dm_map_path)

        # Read dark zone geometry
        with fits.open(probe_filename) as probe_info:
            self.log.info("Loading Dark Zone geometry from {}".format(probe_filename))
            self.dark_zone = hcipy.Field(np.asarray(probe_info['DARK_ZONE'].data, bool).ravel(), stroke_min.focal_grid)

            self.dz_rin = probe_info[0].header.get('DZ_RIN', '?')
            self.dz_rout = probe_info[0].header.get('DZ_ROUT', '?')

    def run_flux_normalization(self, devices):

        # Calculate flux attenuation factor between direct+ND and coronagraphic images
        self.flux_norm_dir = stroke_min.capture_flux_attenuation_data(wavelengths=[self.wvln],
                                                                      out_path=self.output_path,
                                                                      nd_direct={self.wvln: self.nd_direct},
                                                                      nd_coron={self.wvln: self.nd_coron},
                                                                      devices=devices,
                                                                      dm1_act=self.dm1_actuators,
                                                                      dm2_act=self.dm2_actuators,
                                                                      num_exp=self.num_exposures,
                                                                      file_mode=self.file_mode,
                                                                      raw_skip=self.raw_skip)

    def take_exposure(self, devices, exposure_type, wavelength, initial_path, flux_attenuation_factor=1., suffix=None,
                      dm1_actuators=None, dm2_actuators=None, exposure_time=None, auto_expose=None, **kwargs):

        """
        Take an exposure on HiCAT. Scavanged from BroadbandStrokeMinimization.py

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
                nd_filter_set = {self.wvln: self.nd_coron}
            else:
                nd_filter_set = {self.wvln: self.nd_direct}

            move_filter(wavelength=int(np.rint(wavelength)), nd=nd_filter_set[wavelength], devices=devices)

        image, header = stroke_min.take_exposure_hicat(
            dm1_actuators, dm2_actuators, devices, wavelength=wavelength,
            exposure_type=exposure_type, exposure_time=exposure_time, auto_expose=auto_expose,
            initial_path=initial_path, num_exposures=self.num_exposures, suffix=suffix,
            file_mode=self.file_mode, raw_skip=self.raw_skip,
            **kwargs)

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

    def measure_coronagraph_floor(self, devices):
        """
        Take a direct image to save its peak as the normalization factor - with flat Boston DMs.
        Take an unaberrated coronagraphic image to save its mean contrast as coronagraph floor - with stroke min DM
        solution applied to the Boston DMs.
        """

        # Take starting reference images, in direct and coron
        initial_path = os.path.join(self.output_path, 'unaberrated_reference')

        # Need flat DM without SM solution for direct reference images
        dm_acts_zeros = np.zeros(952)

        image_direct, _ = self.take_exposure(devices, 'direct', self.wvln, initial_path, self.flux_norm_dir[self.wvln],
                                             dm1_actuators=dm_acts_zeros, dm2_actuators=dm_acts_zeros)
        self.direct_max = image_direct.max()

        self.image_unaberrated, header = self.take_exposure(devices, 'coron', self.wvln, initial_path,
                                                            dark_zone_mask=self.dark_zone)
        self.image_unaberrated /= self.direct_max

        # Measure coronagraph floor
        self.coronagraph_floor = np.mean(self.image_unaberrated[self.dark_zone])
        try:
            with open(os.path.join(initial_path, 'coronagraph_floor.txt'), 'w') as file:
                file.write(f'Coronagraph floor: {self.coronagraph_floor}')
        except FileNotFoundError:
            with open(os.path.join(self.output_path, 'coronagraph_floor.txt'), 'w') as file:
                file.write(f'Coronagraph floor: {self.coronagraph_floor}')

    def experiment(self):
        raise NotImplementedError("The main PASTIS experiment class does not implement an actual experiment.")
