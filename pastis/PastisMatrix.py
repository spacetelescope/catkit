import hicat.simulators

from astropy.io import fits
import hcipy
import matplotlib.pyplot as plt
import numpy as np
import os

from hicat.config import CONFIG_INI
from hicat.experiments.modules import pastis_functions
from hicat.experiments.pastis.PastisExperiment import PastisExperiment
from hicat.hardware import testbed_state
import hicat.util

import pastis.util
from pastis.matrix_building_numerical import pastis_from_contrast_matrix
from pastis.plotting import plot_pastis_matrix


class PastisMatrix(PastisExperiment):

    name = "PASTIS Matrix"

    def __init__(self, zernike, calibration_aberration, probe_filename, dm_map_path, color_filter, nd_direct, nd_coron,
                 num_exposures, exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                 align_lyot_stop=True, run_ta=True):
        """
        Measure a PASTIS matrix on hardware.
        
        :param zernike: str, which local Zernike to apply to IrisAO, has to be 'piston', 'tip' or 'tilt'
        :param calibration_aberration: float, calibration aberration for PASTIS matrix in meters
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
        :param raw_skip: int, Skips x writing-files for every one taken. raw_skip=math.inf will skip all and save no raw image files
        :param align_lyot_stop: bool, whether to automatically align the Lyot stop before the experiment or not
        :param run_ta: bool, whether to run target acquisition. Will still just measure TA if False.
        """
        super().__init__(probe_filename, dm_map_path, color_filter, nd_direct, nd_coron, num_exposures,
                         exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                         align_lyot_stop, run_ta)

        self.zernike = zernike   # Can only be piston, tip or tilt on hardware. Will determine calibartion aberration position in list of IrisAO command
        self.calib_aberration = calibration_aberration   # in METERS
        if self.zernike not in ('piston', 'tip', 'tilt'):
            raise AttributeError("The local aberration set with self.zernike can only be 'piston', 'tip' or 'tilt'.")

        # Values for calculation of PASTIS matrix
        self.mean_contrasts_image = []
        self.contrast_contribution_per_pair = []    # this is for mean contrast minus the coronagraph floor
        self.aberrated_segment_pairs = []

        self.contrast_contribution_matrix = np.zeros([self.nb_seg, self.nb_seg])

    def experiment(self):

        # A couple of initial log messages
        self.log.info(f'wfe_aber: {self.calib_aberration} m')
        self.log.info(f'Total number of segment pairs in HiCAT pupil: {len(list(pastis.util.segment_pairs_all(self.nb_seg)))}')
        self.log.info(
            f'Non-repeating pairs in HiCAT pupil calculated here: {len(list(pastis.util.segment_pairs_non_repeating(self.nb_seg)))}')

        # Access devices for reference images
        devices = testbed_state.devices.copy()

        # Run flux normalization
        self.log.info('Starting flux normalization')
        self.run_flux_normalization(devices)

        # Take unaberrated direct and coro images, save normalization factor and coro_floor as attributes
        self.log.info('Measuring reference PSF (direct) and coronagraph floor')
        self.measure_coronagraph_floor(devices)

        #iris_dm = devices['iris_dm']    # TODO: Is this how I will access the IrisDM?
        matrix_data_path = os.path.join(self.output_path, 'pastis_matrix')

        ### Measure contrast matrix

        # Instantiate a connection to the IrisAO
        iris_dm = pastis_functions.IrisAO()

        # for loop over all segment pairs
        self.log.info('Start measuring contrast matrix')
        for pair in pastis.util.segment_pairs_non_repeating(self.nb_seg):

            # Set iteration path
            self.log.info(f'Measuring aberrated pair {pair[0]}-{pair[1]}')
            initial_path = os.path.join(matrix_data_path, f'pair_{pair[0]}-{pair[1]}')

            # Make sure the IrisAO is flat
            iris_dm.flatten()

            # TODO: make it such that we can pick between piston, tip and tilt
            # Aberrate pair of segments on IrisAO, piston only for now
            iris_dm.set_actuator(pair[0], self.calib_aberration, 0, 0)    # calibration aberration needed in meters
            if pair[0] != pair[1]:    # if we are on the matrix diagonal, aberrate the segment only once
                iris_dm.set_actuator(pair[1], self.calib_aberration, 0, 0)

            # TODO: save IrisAO WFE maps

            # Take coro image
            pair_image, header = self.take_exposure(devices, 'coron', self.wvln, initial_path, dark_zone_mask=self.dark_zone)
            pair_image /= self.direct_max

            # Measure average contrast in DH
            mean_contrast_this_iteration = np.mean(pair_image[self.dark_zone])
            self.mean_contrasts_image.append(mean_contrast_this_iteration)
            self.contrast_contribution_per_pair.append(mean_contrast_this_iteration - self.coronagraph_floor)
            # Append tuple of the aberrated segment pair
            self.aberrated_segment_pairs.append((pair[0], pair[1]))

            # Fill according entry in the contrast matrix
            self.contrast_contribution_matrix[pair[0], pair[1]] = self.contrast_contribution_per_pair[-1]

        # Save out contrast matrix as fits and pdf
        self.log.info(f"Save measured contrast matrix to {os.path.join(self.output_path, 'pair-wise_contrasts.fits')}")
        hicat.util.write_fits(self.contrast_contribution_matrix, os.path.join(self.output_path, 'pair-wise_contrasts.fits'))
        plt.figure(figsize=(10, 10))
        plt.imshow(self.contrast_contribution_matrix)
        plt.colorbar()
        plt.savefig(os.path.join(self.output_path, 'contrast_matrix.pdf'))
        # TODO: format this figure a little better; decide where I want to have the origin

    def post_experiment(self, *args, **kwargs):

        # Calculate the PASTIS matrix from the contrast matrix: off-axis elements, symmetrize and normalization
        self.log.info('Calculate PASTIS matrix from measured contrast matrix')
        # calibration aberration needed in meters
        self.pastis_matrix = pastis_from_contrast_matrix(self.contrast_contribution_matrix, self.seglist, self.calib_aberration)

        # Save matrix to fits file - this is in units of contrast/nm^2
        hicat.util.write_fits(self.pastis_matrix, os.path.join(self.output_path, 'pastis_matrix.fits'))
        # Plot and save PASTIS matrix as figure
        plot_pastis_matrix(self.pastis_matrix, wvln=self.wvln, out_dir=self.output_path, save=True)
        self.log.info(f'PASTIS matrix saved to: {os.path.join(self.output_path, "pastis_matrix.fits/pdf")}')
