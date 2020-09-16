import hicat.simulators

from astropy.io import fits
import hcipy
import numpy as np
import os

from hicat.experiments.Experiment import HicatExperiment
from hicat.hardware import testbed_state
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
                 num_exposures, file_mode, raw_skip, align_lyot_stop=True, run_ta=True):
        super().__init__()
        self.probe_filename = probe_filename  # needed for DH geometry only
        self.dm_map_path = dm_map_path  # will need to load these DM maps to get to low contrast (take from good PW+SM run)
        self.align_lyot_stop = align_lyot_stop
        self.run_ta = run_ta

        self.color_filter = color_filter
        self.nd_direct = nd_direct
        self.nd_coron = nd_coron
        self.num_exposures = num_exposures
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