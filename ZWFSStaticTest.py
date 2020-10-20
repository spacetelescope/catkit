from hicat.experiments.Experiment import HicatExperiment
from hicat.control import zwfs
import logging

import numpy as np
import glob
from catkit.hardware.boston import DmCommand
from astropy.io import fits

class ZWFSStaticTest(HicatExperiment):
    name = "Take ZWFS static test"
    log = logging.getLogger(__name__)

    def __init__(self,
                 instrument='HICAT',
                 wave=640e-9,
                 filename='ZWFS',
                 align_lyot_stop=False,
                 run_ta=True):

        """
        Performs a calibration and a phase measurement with the ZWFS.
        :param instrument:  (str) name of the pyZELDA file to load the info from the sensor
        :param wave: (float) wavelength of operation, in meters
                 WARNING: pyZELDA convention uses wavelengths in meters !!!
        :param filename: (str) name of the file saved on disk
        """

        super().__init__()
        self.filename = filename
        self.wave = wave
        self.instrument = instrument
        self.align_lyot_stop = align_lyot_stop
        self.run_ta = run_ta

    def experiment(self):
        '''
        Aberrations are ranked:
        - focus
        - astig 45
        - astig 0
        - coma y
        - coma x
        - trefoil y
        - trefoil x
        - spherical
        '''

        dm1_shape = fits.getdata()
        dm_path = 'Z:/Testbeds/hicat_dev/data_vault/dm_calibration/dm2_calibration/'

        aberration_path = ['2018-01-21T09-34-00_4d_zernike_loop_focus/',
                           '2018-01-21T12-07-16_4d_zernike_loop_astigmatism45/',
                           '2018-01-21T12-37-21_4d_zernike_loop_astigmatism0/',
                           '2018-01-21T13-08-00_4d_zernike_loop_comay/',
                           '2018-01-21T13-39-31_4d_zernike_loop_comax/',
                           '2018-01-21T14-10-45_4d_zernike_loop_trefoily/',
                           '2018-01-21T14-41-48_4d_zernike_loop_trefoilx/',
                           '2018-01-21T15-13-01_4d_zernike_loop_spherical/']

        aberration_values = ['20_nm_p2v/',
                             '40_nm_p2v/',
                             '80_nm_p2v/']

        file_names = ['Focus_zernike_volts_dm2.fits',
                      'Astigmatism_45_zernike_volts_dm2.fits',
                      'Astigmatism_0_zernike_volts_dm2.fits',
                      'Coma_Y_zernike_volts_dm2.fits',
                      'Coma_X_zernike_volts_dm2.fits',
                      'Trefoil_Y_zernike_volts_dm2.fits',
                      'Trefoil_X_zernike_volts_dm2.fits',
                      'Spherical_zernike_volts_dm2.fits']

        zernike_sensor = zwfs.ZWFS(self.instrument)
        zernike_sensor.calibrate(output_path=self.output_path)
        zernike_sensor.save_list(zernike_sensor._clear_pupil, 'ZWFS_clear_pupil_flat_dms', self.output_path)

        dm1_calibrated = np.zeros((34,34)) # Read from calibrated folders

        dm2_flat = np.zeros((34,34))

        basis = np.nan_to_num(zwfs.ztools.zernike.zernike_basis(nterms=nb_aberrations, npix=34)*1e-9)

        zopd_stacks = []

        zernike_sensor.make_reference_opd(self.wave, dm1_shape=dm1_calibrated, dm2_shape=dm2_flat)

        for i, aberration in enumerate(aberration_path):
            for p2v in aberration_values:
                dm2_shape = fits.getdata(dm_path+aberration+p2v+file_names[i])

                zopd = zernike_sensor.perform_zwfs_measurement(self.wave, output_path=self.output_path,
                                                               differential=True, dm1_shape=dm1_calibrated,
                                                               dm2_shape=dm2_shape, file_mode=True)

        zopd_stacks.append(zopd)

        zopd_array = np.array(zopd_stacks)
        zernike_sensor.save_list(zernike_sensor._reference_opd, 'ZWFS_reference_opd', self.output_path)

        zernike_sensor.save_list(zopd_array, 'ZWFS_aberration_opd', self.output_path)
