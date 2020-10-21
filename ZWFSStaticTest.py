from hicat.experiments.Experiment import HicatExperiment
from hicat.control import zwfs
import logging

import numpy as np
from catkit.hardware.boston.commands import flat_command
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

        dm1_command = flat_command(bias=False, flat_map=True, dm_num=1)


        dm_path = 'Z:/Testbeds/hicat_dev/data_vault/dm_calibration/dm2_calibration/'
        #dm_path = '/home/rpourcelot/hicat_dev/data_vault/dm_calibration/dm2_calibration/'
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

        suffix = 'iteration19/dm_command/dm_command_2d_noflat.fits'

        file_names = ['Focus_zernike_volts_dm2',
                      'Astigmatism_45_zernike_volts_dm2',
                      'Astigmatism_0_zernike_volts_dm2',
                      'Coma_Y_zernike_volts_dm2',
                      'Coma_X_zernike_volts_dm2',
                      'Trefoil_Y_zernike_volts_dm2',
                      'Trefoil_X_zernike_volts_dm2',
                      'Spherical_zernike_volts_dm2']

        dm2_flat = flat_command(bias=False, flat_map=True, dm_num=2)

        zernike_sensor = zwfs.ZWFS(self.instrument)
        zernike_sensor.calibrate(output_path=self.output_path, dm1_shape=dm1_command, dm2_shape=dm2_flat)
        zernike_sensor.save_list(zernike_sensor._clear_pupil, 'ZWFS_clear_pupil_dms', self.output_path)
        
        #basis = np.nan_to_num(zwfs.ztools.zernike.zernike_basis(nterms=nb_aberrations, npix=34)*1e-9)

        zopd_stacks = np.zeros((len(aberration_path), len(aberration_values), zernike_sensor._array_diameter, zernike_sensor._array_diameter))

        zernike_sensor.make_reference_opd(self.wave, dm1_shape=dm1_command, dm2_shape=dm2_flat)

        for i, aberration in enumerate(aberration_path):
            for j, p2v in enumerate(aberration_values):
                dm2_shape = fits.getdata(dm_path+aberration+p2v+suffix)
                dm2_command = DmCommand.DmCommand(dm2_shape, dm_num=2, flat_map=True, bias=False)

                zopd = zernike_sensor.perform_zwfs_measurement(self.wave, output_path=self.output_path,
                                                               differential=True, dm1_shape=dm1_command,
                                                               dm2_shape=dm2_command, file_mode=True,
                                                               filename=file_names[i]+p2v[:-1])

                zopd_stacks[i, j] = zopd.copy()
                zernike_sensor.save_list(zopd, 'ZWFS_OPD'+file_names[i]+p2v[:-1], self.output_path+'/'+file_names[i])
                #fits.writeto('/mnt/c/Users/rpourcelot/Documents/zopd.fits', zopd)


        # Save the files
        np.save(self.output_path + '/' + 'zopd_stacks.npy', zopd_stacks)

        zernike_sensor.save_list(zernike_sensor._reference_opd, 'ZWFS_reference_opd', self.output_path)
