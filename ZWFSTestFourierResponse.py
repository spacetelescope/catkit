from hicat.experiments.Experiment import HicatExperiment
from hicat.control import zwfs
import logging

import numpy as np
import scipy.optimize as so
import matplotlib.pyplot as plt

class ZWFSTestFourierResponse(HicatExperiment):
    name = "Take ZWFS fourier response test"
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

        def fourier_ab(fx, fy):

            def funab(pup, a, b):
                dim = pup.shape[0]
                x = np.arange(dim)
                xx, yy = np.meshgrid(x, x)
                xx, yy = xx / dim, yy / dim

                xx, yy = xx * 2 * np.pi * fx, yy * 2 * np.pi * fy

                return ((a * np.sin(xx + yy) + b * np.cos(xx + yy)) * pup).reshape((dim ** 2))

            return funab

        zernike_sensor = zwfs.ZWFS(self.instrument)

        nb_freq = 20
        freq_max = 7
        freq_min = 3
        freqx = np.linspace(freq_min, freq_max, nb_freq)
        freqy = np.linspace(freq_min, freq_max ,nb_freq)
        aamp = 1e-8
        bamp = 1e-8

        dm_pup = zwfs.aperture.disc(34, 34, diameter=True)

        zernike_sensor.calibrate(output_path=self.output_path)
        zernike_sensor.make_reference_opd(self.wave)

        ab_stack = np.zeros((nb_freq, nb_freq, 2))

        for i, fx in enumerate(freqx):
            for j, fy in enumerate(freqy):
                fourier_fun = fourier_ab(fx, fy)
                dm_shape = fourier_fun(dm_pup, aamp, bamp).reshape((34,34))
                zopd = zernike_sensor.perform_zwfs_measurement(self.wave,
                                                               output_path=self.output_path,
                                                               differential=True,
                                                               dm1_shape=dm_shape,
                                                               file_mode=False).squeeze()

                final_roi = zwfs.aperture.disc(zernike_sensor.pupil_diameter, zernike_sensor.pupil_diameter, diameter=True)
                array_dim = zopd.shape[-1]
                pup_dim = zernike_sensor.pupil_diameter
                cropped_zopd = zopd[(array_dim-pup_dim)//2:(array_dim+pup_dim)//2,
                               (array_dim-pup_dim)//2:(array_dim+pup_dim)//2]

                ab_fit, _ = so.curve_fit(fourier_fun, final_roi, cropped_zopd.reshape(zernike_sensor.pupil_diameter**2))
                reference_fit, _ = so.curve_fit(fourier_fun, dm_pup, dm_shape.reshape(34*34))
                ab_stack[i,j] = ab_fit / reference_fit * 1e-9

        plt.figure(figsize=(20,10))
        plt.semilogy(freqx, abs(ab_stack[0, :, 0]))
        plt.semilogy(freqy, abs(ab_stack[:, 0, 0]))
        plt.xlabel('Spatial frequency (c/p)')
        plt.ylabel('Fitted coefficient')
        plt.legend(['x frequencies', 'y frequencies'])

        plt.savefig(self.output_path+'/frequency_plot.pdf')
        np.save(self.output_path+'numpy_ab_stack', ab_stack)
        zernike_sensor.save_list(zopd, 'ZWFS_res', self.output_path)


