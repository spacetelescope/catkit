import hicat.simulators
import glob
import os
from astropy.io import fits
import hcipy
import numpy as np

from hicat.config import CONFIG_INI
from hicat.experiments.Experiment import HicatExperiment
from hicat.hardware import testbed_state
from hicat.hardware.testbed import move_filter
from hicat.wfc_algorithms import stroke_min

import pastis.util_pastis


def read_dm_commands(dm_command_directory):
    """Hijacked partially from StrokeMinimization.restore_last_strokemin_dm_shapes()"""
    surfaces = []
    for dmnum in [1, 2]:
        actuators_2d = fits.getdata(os.path.join(dm_command_directory, 'dm{}_command_2d_noflat.fits'.format(dmnum)))
        actuators_1d = actuators_2d.ravel()[stroke_min.dm_mask]
        actuators_1d *= 1e9  # convert from meters to nanometers # FIXME this is because of historical discrepancies, need to unify everything at some point
        surfaces.append(actuators_1d)
    return surfaces


class PastisExperiment(HicatExperiment):

    name = 'PASTIS Experiment'

    def __init__(self, probe_filename, dm_map_path, color_filter, nd_direct, nd_coron,
                 num_exposures, exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                 align_lyot_stop=True, run_ta=True):
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
        self.seglist = pastis.util_pastis.get_segment_list('HiCAT')
        self.wvln = 640    # nm
        self.log.info(f'Number of segments: {self.nb_seg}')
        self.log.info(f'Segment list: {self.seglist}')

        # Read DM commands, treated as part of the coronagraph
        self.dm1_actuators, self.dm2_actuators = read_dm_commands(self.dm_map_path)

        # Read dark zone geometry
        with fits.open(probe_filename) as probe_info:
            self.log.info("Loading Dark Zone geometry from {}".format(probe_filename))
            self.dark_zone = hcipy.Field(np.asarray(probe_info['DARK_ZONE'].data, bool).ravel(), stroke_min.focal_grid)

            self.dz_rin = probe_info[0].header.get('DZ_RIN', '?')
            self.dz_rout = probe_info[0].header.get('DZ_ROUT', '?')

    def run_flux_normalization(self):

        # Access devices for flux normalization
        devices = testbed_state.devices.copy()

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
                nd_filter_set = self.nd_coron
            else:
                nd_filter_set = self.nd_direct

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

    def measure_coronagraph_floor(self):
        pass

        ### Flux calibration?
        # take direct image
        # norm = normalization factor for coro images

        ### Contrast floor
        # apply DM map from strokemin
        # take coro image, normalize, measure contrast in DH
        # Save coronagraph floor to file

        # return contrast_floor, norm

    def experiment(self):
        raise NotImplementedError("The main PASTIS experiment class does not implement an actual experiment.")