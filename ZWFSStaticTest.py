from hicat.experiments.Experiment import HicatExperiment
from hicat.control import zwfs
import logging


class ZWFSStaticTest(HicatExperiment):
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

        super().__init__()
        self.filename = filename
        self.wave = wave
        self.instrument = instrument
        self.align_lyot_stop = align_lyot_stop
        self.run_ta = run_ta

    def experiment(self):

        zernike_sensor = zwfs.ZWFS(self.instrument)
        zernike_sensor.calibrate(output_path=self.output_path)
        zernike_sensor.make_reference_opd(self.wave)
        zopd = zernike_sensor.perform_zwfs_measurement(self.wave, output_path=self.output_path, differential=True)
        zernike_sensor.save_list(zopd, 'ZWFS_OPD', self.output_path)
