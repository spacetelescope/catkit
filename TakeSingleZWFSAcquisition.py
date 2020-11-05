from hicat.experiments.Experiment import HicatExperiment
from hicat.control import zwfs
import logging
from catkit.hardware.boston import DmCommand

import numpy as np

class TakeSingleZWFSAcquisition(HicatExperiment):
    name = "Take ZWFS single measurement"
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

        super().__init__(run_ta=run_ta, align_lyot_stop=align_lyot_stop)
        self.filename = filename
        self.wave = wave
        self.instrument = instrument

    def experiment(self):

        F = np.zeros((34, 34))
        F[16:20, 12:23] = 1
        F[5:9, 12:26] = 1
        F[5:29, 12:16] = 1
        F = np.flipud(F) * 1e-7

        # Init the sensor object
        F_shape = DmCommand.DmCommand(F, dm_num=1, bias=False, flat_map=True)
        zernike_sensor = zwfs.ZWFS(self.instrument, wavelength=self.wave)
        zernike_sensor.calibrate(output_path=self.output_path)
        zernike_sensor.make_reference_opd(self.wave)

        # Actual phase measurment
        zopd = zernike_sensor.perform_zwfs_measurement(self.wave, dm1_shape=F_shape, output_path=self.output_path, differential=True)

        #F_shape.save_as_fits(self.output_path+'fits_dm_command.fits')

        # Save files
        zernike_sensor.save_list(zopd, 'ZWFS_OPD', self.output_path)
        zernike_sensor.save_list(F, 'F', self.output_path)
        zernike_sensor.save_list(zernike_sensor._reference_opd, 'ref_OPD', self.output_path)