from hicat.experiments.Experiment import HicatExperiment
from hicat.control import zwfs
import logging


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

        super().__init__()
        self.filename = filename
        self.wave = wave
        self.instrument = instrument
        self.align_lyot_stop = align_lyot_stop
        self.run_ta = run_ta

    def experiment(self):

        zernike_sensor = zwfs.ZWFS(self.instrument)

        # Final boss
        zernike_sensor.calibrate_and_measure(self.wave,
                                             self.filename,
                                             self.output_path)