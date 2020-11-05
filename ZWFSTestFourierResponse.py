from hicat.experiments.Experiment import HicatExperiment
from hicat.control import zwfs
import logging

import numpy as np
import scipy.optimize as so
import matplotlib.pyplot as plt
from astropy.io import fits

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

                return ((a * np.sin(xx + yy) + b * np.cos(xx + yy))*pup).reshape((dim ** 2))

            return funab

        zernike_sensor = zwfs.ZWFS(self.instrument, wavelength=self.wave)

        nb_freqx = 50
        #nb_freqy = nb_freqx
        nb_freqy = 1
        freq_max = 8
        freq_min = 1
        freqx = np.linspace(freq_min, freq_max, nb_freqx)
        freqy = np.linspace(freq_min, freq_max, nb_freqy)

        aamp = 3e-8
        bamp = 1e-8

        dm_pup = zwfs.aperture.disc(34, 34, diameter=True)

        zernike_sensor.calibrate(output_path=self.output_path)
        zernike_sensor.make_reference_opd(self.wave)

        ab_stack = np.zeros((nb_freqx, nb_freqy, 2))
        shapes_stack = np.zeros((nb_freqx, nb_freqy, 34, 34))

        pup_dim = zernike_sensor.pupil_diameter
        zopd_stack = np.zeros((nb_freqx, nb_freqy, pup_dim, pup_dim))

        for i, fx in enumerate(freqx):
            for j, fy in enumerate(freqy):
                fourier_fun = fourier_ab(fx, fy)
                blank_pup = np.ones((34,34))

                #dm_shape = fourier_fun(dm_pup, aamp, bamp).reshape((34,34))
                dm_shape = fourier_fun(blank_pup, aamp, bamp).reshape((34,34))

                shapes_stack[i,j] = dm_shape.copy()

                zopd = zernike_sensor.perform_zwfs_measurement(self.wave,
                                                               output_path=self.output_path,
                                                               differential=True,
                                                               dm1_shape=dm_shape,
                                                               file_mode=False).squeeze()

                final_roi = zwfs.aperture.disc(zernike_sensor.pupil_diameter, zernike_sensor.pupil_diameter, diameter=True)
                array_dim = zopd.shape[-1]

                cropped_zopd = zopd[(array_dim-pup_dim)//2:(array_dim+pup_dim)//2,
                               (array_dim-pup_dim)//2:(array_dim+pup_dim)//2]
                zopd_stack[i,j] = cropped_zopd.copy()

                ab_fit, _ = so.curve_fit(fourier_fun, final_roi, cropped_zopd.reshape(zernike_sensor.pupil_diameter**2))
                reference_fit, _ = so.curve_fit(fourier_fun, dm_pup, dm_shape.reshape(34*34))
                ab_stack[i,j] = ab_fit #/ reference_fit * 1e-9
                fits.writeto(self.output_path+ f'/zopd_x{fx:.2f}_y{fy:.2}.fits', cropped_zopd)

        plt.figure(figsize=(20,10))
        plt.semilogy(freqx, abs(ab_stack[:, 0, 1]), label='x; b_coeff')
        plt.semilogy(freqy, abs(ab_stack[0, :, 1]), label='y; b_coeff')
        plt.semilogy(freqx, abs(ab_stack[:, 0, 0]), label='x; a_coeff')
        plt.semilogy(freqy, abs(ab_stack[0, :, 0]), label='y; a_coeff')
        plt.legend()
        plt.xlabel('Spatial frequency (c/p)')
        plt.ylabel('Fitted coefficient')
        #plt.legend(['x frequencies', 'y frequencies'])
        plt.savefig(self.output_path + '/frequency_plot.pdf')

        plt.figure(figsize=(10,10))
        plt.imshow(np.flipud(abs(ab_stack[:,:,0])), extent=[freq_min, freq_max, freq_min, freq_max])
        plt.savefig(self.output_path+'/2D_plot.pdf')


        np.save(self.output_path+'/dm_shapes', shapes_stack)
        np.save(self.output_path+'/numpy_ab_stack', ab_stack)

        zernike_sensor.save_list(zopd, 'ZWFS_res', self.output_path)


