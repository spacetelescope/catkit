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

        # Define F shape for DM1
        f_shape = np.zeros((34, 34))
        f_shape[5:29, 12:16] = 1
        f_shape[5:9, 12:26] = 1
        f_shape[16:20, 12:23] = 1

        f_shape *= 1e-8

        zernike_sensor = zwfs.ZWFS(self.instrument)
        zernike_sensor.calibrate(output_path=self.output_path)
        zernike_sensor.save_list(zernike_sensor._clear_pupil, 'ZWFS_clear_pupil_flat_dms', self.output_path)
        zernike_sensor.make_reference_opd(self.wave, dm1_shape=f_shape)

        zopd_f = zernike_sensor.perform_zwfs_measurement(self.wave, output_path=self.output_path,
                                                       differential=False, dm1_shape=f_shape, file_mode=False)

        zernike_sensor.save_list(zopd_f, 'ZWFS_F_opd_differential', self.output_path)

        zopd_flat = zernike_sensor.perform_zwfs_measurement(self.wave, output_path=self.output_path,
                                                       differential=False, file_mode=False)
        zernike_sensor.save_list(zopd_flat, 'ZWFS_flat_DM_opd', self.output_path)



       #  defocus map

        #diversity_focus_data_path = "Z:/Testbeds/hicat_dev/data_vault/coffee/coffee_commands/dm2_commands/focus/"
        #diversity_focus_command_paths = glob(diversity_focus_data_path + self.diversity + "/*p2v/*.fits")
        #dm2_command_objects = []
        #for command in diversity_focus_command_paths:
        #    dm2_command_objects.append = DmCommand.load_dm_command(command, bias=False, flat_map=False, dm_num=2,as_volts=True)

        zernike_sensor.calibrate(output_path=self.output_path, filename='dm2_focus')
        #zopd_focus = zernike_sensor.perform_zwfs_measurement(self.wave, output_path=self.output_path,
                                                             #differential=False, dm2_shape=dm2_command_objects[0],
                                                             #dm_command=True)

        #zernike_sensor.save_list(zopd_focus, 'ZWFS_focus_opd', self.output_path)
        zernike_sensor.save_list(zernike_sensor._clear_pupil, 'ZWFS_clear_pupil_defoc_dm2', self.output_path)