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
                 instrument='HiCAT',
                 wave=640e-9,
                 filename='ZWFS',
                 align_lyot_stop=False,
                 run_ta=True):

        """
        Performs a series of measurements with Zernike polynomials on DM2 on top of the flat map.

        :param instrument:  (str) name of the pyZELDA file to load the info from the sensor
        :param wave: (float) wavelength of operation, in meters
                 WARNING: pyZELDA convention uses wavelengths in meters !!!
        :param filename: (str) name of the file saved on disk
        :param align_lyot_stop: (bool) Do align Lyot stop. Useless for ZWFS measurements unless coron images are taken.
         Default at False.
        :param run_ta: (bool) Do run target acquisition. Default is True.
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

        # Define flat command for DM 1&2
        dm1_command = flat_command(bias=False, flat_map=True, dm_num=1)
        dm2_flat = flat_command(bias=False, flat_map=True, dm_num=2)

        # Initialize and calibrate ZWFS with flat DMs
        zernike_sensor = zwfs.ZWFS(wavelength=self.wave, instrument=self.instrument)
        zernike_sensor.calibrate(output_path=self.output_path, dm1_shape=dm1_command, dm2_shape=dm2_flat)
        zernike_sensor.save_list(zernike_sensor._clear_pupil, 'ZWFS_clear_pupil_dms', self.output_path)

        # Perform reference OPD measurement with flat DMs
        zernike_sensor.make_reference_opd(self.wave, dm1_shape=dm1_command, dm2_shape=dm2_flat)
        zernike_sensor.save_list(zernike_sensor._reference_opd, 'ZWFS_reference_opd', self.output_path)

        # Aberration names for saving and tracking
        file_names = ['Tip_dm2',
                      'Tilt_dm2',
                      'Focus_dm2',
                      'Astigmatism_45_zernike_volts_dm2',
                      'Astigmatism_0_zernike_volts_dm2',
                      'Coma_Y_zernike_volts_dm2',
                      'Coma_X_zernike_volts_dm2',
                      'Trefoil_Y_zernike_volts_dm2',
                      'Trefoil_X_zernike_volts_dm2',
                      'Spherical_zernike_volts_dm2']



        # Take TA image for PSF diagnostic FIXME: crop not centered on PSF
        ta_diag, _ = zernike_sensor.take_exposure_ta_diagnostic(output_path=self.output_path,
                                                                dm1_shape=dm1_command,
                                                                dm2_shape=dm2_flat,
                                                                file_mode=True)


        # Initialize aberration basis
        nb_aberrations = 11
        basis = np.nan_to_num(zwfs.ztools.zernike.zernike_basis(nterms=nb_aberrations, npix=34)*1e-9)
        pure_zernikes_values = [2, 7, 15] # RMS values in nm

        # Initialize stack array for OPDs
        zopd_stacks = np.zeros((nb_aberrations, len(pure_zernikes_values),
                                zernike_sensor._array_diameter, zernike_sensor._array_diameter))


        # Actual loop on aberrations and aberrations values
        for i, aberration in enumerate(basis[1:nb_aberrations]):

            for j, val in enumerate(pure_zernikes_values):

                p2v = str(val)+'RMS'

                # Create DM shape & save it
                dm2_shape = val*aberration
                zernike_sensor.save_list(dm2_shape, 'dm2_command' + file_names[i] + p2v[:-1],
                                         self.output_path + '/' + file_names[i])

                # Convert to DM command
                dm2_command = DmCommand.DmCommand(dm2_shape, flat_map=True, bias=False, dm_num=2)

                #Check TA images - FIXME: ROI to be adjusted
                #ta_diag, _ = zernike_sensor.take_exposure_ta_diagnostic(output_path=self.output_path,
                #                                                        dm1_shape=dm1_command,
                #                                                        dm2_shape=dm2_command,
                #                                                        file_mode=True)

                # Perform the actual phase measurement
                zopd = zernike_sensor.perform_zwfs_measurement(self.wave, output_path=self.output_path,
                                                               differential=True, dm1_shape=dm1_command,
                                                               dm2_shape=dm2_command, file_mode=True,
                                                               filename=file_names[i]+p2v[:-1])

                # Store it
                zopd_stacks[i, j] = zopd.copy()
                zernike_sensor.save_list(zopd, 'ZWFS_OPD'+file_names[i]+p2v[:-1], self.output_path+'/'+file_names[i])