import hicat.simulators

from astropy.io import fits
import hcipy
import numpy as np

from hicat.config import CONFIG_INI
from hicat.experiments.pastis.PastisExperiment import PastisExperiment

import pastis.util_pastis
from pastis.matrix_building_numerical import pastis_from_contrast_matrix
from pastis.plotting import plot_pastis_matrix


class PastisMatrix(PastisExperiment):

    name = "PASTIS Matrix"

    def __init__(self, zernike, calibration_aberration, probe_filename, dm_map_path, color_filter, nd_direct, nd_coron,
                 num_exposures, file_mode, raw_skip, align_lyot_stop=True, run_ta=True):
        super().__init__(probe_filename, dm_map_path, color_filter, nd_direct, nd_coron,
                 num_exposures, file_mode, raw_skip, align_lyot_stop, run_ta)

        self.zernike = zernike   # Can only be piston, tip or tilt on hardware. Will determine calibartion aberration position in list of IrisAO command
        self.calib_aberration = calibration_aberration   # in METERS

        self.log.info(f'wfe_aber: {self.calib_aberration} m')
        self.log.info(f'Total number of segment pairs in HiCAT pupil: {len(list(pastis.util_pastis.segment_pairs_all(self.nb_seg)))}')
        self.log.info(
            f'Non-repeating pairs in HiCAT pupil calculated here: {len(list(pastis.util_pastis.segment_pairs_non_repeating(self.nb_seg)))}')

        # Values for calculation of PASTIS matrix
        self.mean_contrasts_image = []
        self.aberrated_segment_pairs = []

    def experiment(self):
        # Run flux normalization
        self.run_flux_normalization()

        # Save used DM maps into self.output_path

        #coro_floor, norm = self.measure_coronagraph_floor()

        ### Measure contrast matrix
        # for loop over all segment pairs
        # aberrate IrisAO
        # take image
        # measure average contrast in DH
        #self.mean_contrasts_image.append(np.mean(image_before[self.dark_zone]))
        # subtract contrast floor
        # save out contrast matrix

        ### Calculate PASTIS matrix
        # Calculate the PASTIS matrix from the contrast matrix: off-axis elements and normalization
        #matrix_pastis = pastis_from_contrast_matrix(contrast_matrix, self.seglist, self.calib_aberration)

        # Save matrix to fits file
        # This is in units of c/nm^2

        # Plot and save PASTIS matrix as figure
        #plot_pastis_matrix(matrix_pastis, wvln=self.wvln, out_dir=self.output_path, save=True)