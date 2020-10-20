from hicat.experiments.Experiment import HicatExperiment
from hicat.control import zwfs
import logging

import numpy as np
import glob
from catkit.hardware.boston import DmCommand

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

        zernike_sensor = zwfs.ZWFS(self.instrument)
        zernike_sensor.calibrate(output_path=self.output_path)
        zernike_sensor.save_list(zernike_sensor._clear_pupil, 'ZWFS_clear_pupil_flat_dms', self.output_path)

        dm1_calibrated = np.zeros((34,34)) # Read from calibrated folders

        dm2_flat = np.zeros((34,34))

        nb_aberrations = 5
        dm2_calibrated = np.zeros((nb_aberrations, 34,34)) # Read calibration

        basis = np.nan_to_num(zwfs.ztools.zernike.zernike_basis(nterms=nb_aberrations, npix=34)*1e-9)

        zopd_stacks = []

        zernike_sensor.make_reference_opd(self.wave, dm1_shape=dm1_calibrated, dm2_shape=dm2_flat)

        for dm2_shape in basis:
            zopd = zernike_sensor.perform_zwfs_measurement(self.wave, output_path=self.output_path,
                                                           differential=True, dm1_shape=dm1_calibrated,
                                                           dm2_shape=dm2_shape, file_mode=True)
            zopd_stacks.append(zopd)

        zopd_array = np.array(zopd_stacks)
        zernike_sensor.save_list(zernike_sensor._reference_opd, 'ZWFS_reference_opd', self.output_path)

        zernike_sensor.save_list(zopd_array, 'ZWFS_aberration_opd', self.output_path)
