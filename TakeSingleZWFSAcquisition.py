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


        if 0:
            prefix = 'take_exposure'
            zernike_sensor._nbframes = 1
            out, _ = zernike_sensor.take_exposure()

        if 0:
            prefix = 'take_multiple_exposures'
            zernike_sensor._nbframes = 10
            out, _ = zernike_sensor.take_exposure()

        if 0:
            prefix = 'move_mask_nominal'
            zernike_sensor.xpos = 'nominal'
            out, _ = zernike_sensor.take_exposure()

        if 0:
            prefix = 'move_mask_ofb'
            zernike_sensor.xpos = 'out_of_beam'
            out, _ = zernike_sensor.take_exposure()

        if 0:
            prefix = 'take_dark'
            out = zernike_sensor.take_dark()

        if 0:
            prefix = 'dm_control'
            out = zernike_sensor.take_exposure_dm(dm1_shape=zernike_sensor.sin_shape)

        if 0:
            prefix = 'calibrate'
            dark = zernike_sensor.take_dark()
            zernike_sensor.calibrate(dark)
            out = zernike_sensor._clear_pupil

        #zernike_sensor.save_list(out, prefix, self.output_path)

        # Final boss
        if 1:
            zernike_sensor.calibrate_and_measure(self.wave,
                                                       self.filename,
                                                       self.output_path)