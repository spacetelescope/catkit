from hicat.experiments.Experiment import HicatExperiment
from hicat.control import zwfs
import logging

import numpy as np
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

        # Define F shape for DM1
        f_shape = np.zeros((34, 34))
        f_shape[5:29, 12:16] = 1
        f_shape[5:9, 12:26] = 1
        f_shape[16:20, 12:23] = 1

        f_shape *= 1e-8

        zernike_sensor = zwfs.ZWFS(self.instrument)
        zernike_sensor.calibrate(output_path=self.output_path)
        zernike_sensor.make_reference_opd(self.wave, dm1_shape=f_shape)
        zopd = zernike_sensor.perform_zwfs_measurement(self.wave, output_path=self.output_path,
                                                       differential=True, dm1_shape=f_shape)

        zernike_sensor.save_list(zopd, 'ZWFS_F_opd_differential', self.output_path)

