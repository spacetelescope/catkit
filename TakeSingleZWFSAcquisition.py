from hicat.experiments.Experiment import HicatExperiment
from hicat.control import zwfs
from hicat.wfc_algorithms import wfsc_utils
import logging
from catkit.hardware.boston import DmCommand
from astropy.io import fits
import numpy as np



class TakeSingleZWFSAcquisition(HicatExperiment):
    name = "Take ZWFS single measurement"
    log = logging.getLogger(__name__)

    def __init__(self,
                 instrument='HiCAT',
                 wave=640e-9,
                 filename='ZWFS',
                 align_lyot_stop=False,
                 run_ta=True):

        """
        Performs a single ZWFS acquisitions with calibration and reference OPD. Current introduced shape is F on DM1
        and DM2 one by one.
        This is a simple example on how to use the ZWFS.

        :param instrument:  (str) name of the pyZELDA file to load the info from the sensor
        :param wave: (float) wavelength of operation, in meters
                 WARNING: pyZELDA convention uses wavelengths in meters !!!
        :param filename: (str) name of the file saved on disk
        :param align_lyot_stop: (bool) Do align Lyot stop. Useless for ZWFS measurements unless coron images are taken.
         Default at False.
        :param run_ta: (bool) Do run target acquisition. Default is True.
        """

        super().__init__(run_ta=run_ta, align_lyot_stop=align_lyot_stop)
        self.filename = filename
        self.wave = wave
        self.instrument = instrument

    def experiment(self):

        # Build a F map
        f_array = np.zeros((34, 34))
        f_array[16:20, 12:23] = 1
        f_array[5:9, 12:26] = 1
        f_array[5:29, 12:16] = 1

        f_array = 5e-8 * f_array

        # Init the sensor object for both DMs
        f_shape = DmCommand.DmCommand(f_array, dm_num=1, bias=False, flat_map=True)
        f_shape2 = DmCommand.DmCommand(f_array, dm_num=2, bias=False, flat_map=True)

        # Initialize Zernike sensor object
        zernike_sensor = zwfs.ZWFS(wavelength=self.wave, instrument=self.instrument)

        # Calibrate ZWFS with clear frame / flat maps on both DMs
        zernike_sensor.calibrate(output_path=self.output_path)

        # Perform reference OPD measurement
        zernike_sensor.make_reference_opd(self.wave)

        # Actual phase measurment with introduced F on DM1
        zopd = zernike_sensor.perform_zwfs_measurement(self.wave, dm1_shape=f_shape, output_path=self.output_path,
                                                       differential=True, file_mode=True)

        # Phase measurement with introduced F on DM2
        zopd2 = zernike_sensor.perform_zwfs_measurement(self.wave, dm2_shape=f_shape2, output_path=self.output_path,
                                                        differential=True, file_mode=True)
        # Save files
        # -------------

        # Reference OPD
        zernike_sensor.save_list(zernike_sensor._reference_opd, 'ref_OPD', self.output_path)

        # OPD with F on DM1
        zernike_sensor.save_list(zopd, 'ZWFS_OPD_F1', self.output_path)

        # OPD with F on DM2
        zernike_sensor.save_list(zopd2, 'ZWFS_OPD_F2', self.output_path)

        # F shape
        zernike_sensor.save_list(f_array, 'F', self.output_path)
