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
                 instrument='HiCAT',
                 wave=640e-9,
                 filename='ZWFS',
                 align_lyot_stop=False,
                 run_ta=True):

        """
        Performs a series of measurements with various sinusoidal shapes on DM1 to plot the response of the system
        {FPM filter + ZWFS}.

        :param instrument:  (str) name of the pyZELDA file to load the info from the sensor
        :param wave: (float) wavelength of operation, in meters
                 WARNING: pyZELDA convention uses wavelengths in meters !!!
        :param filename: (str) name of the file saved on disk
        :param align_lyot_stop: (bool) Do align Lyot stop. Useless for ZWFS measurements unless coron images are taken.
         Default at False.
        :param run_ta: (bool) Do run target acquisition. Default is True.
        """

        super().__init__()
        self.filename = filename
        self.wave = wave
        self.instrument = instrument
        self.align_lyot_stop = align_lyot_stop
        self.run_ta = run_ta

    def experiment(self):

        def fourier_ab(fx, fy):
            """
            Create a function that can draw a sinusoidal shape of given vertical and horizontal frequencies.

            :param fx: (float) Horizontal spatial frequency, in cycles/pupil.
            :param fy: (float) Vertical spatial frequency, in cycles/pupil.

            :returns funab: (function) Function that draws sinusoidal shapes on the given pupil under the form a*sin + b*cos
            """
            def funab(pup, a, b):
                """
                Function to draw sinusoidal shapes on given pupil.

                :param pup: (2d array) pupil on which to produce the sinusoid
                :param a: (float) amplitude of the odd part (sinus) of the sinusoid
                :param b: (float) amplitude of the even part (cosinus) of the sinusoid
                :return: (1d array) The sinusoidal shape drawn on the ravelled pupil.
                """

                dim = pup.shape[0]

                # Create coordinate arrays
                x = np.arange(dim)
                x -= x[dim//2]
                xx, yy = np.meshgrid(x, x)
                xx, yy = xx / dim, yy / dim

                xx, yy = xx * 2 * np.pi * fx, yy * 2 * np.pi * fy

                # Draw the sin / cos and reshape
                return ((a * np.sin(xx + yy) + b * np.cos(xx + yy))*pup).reshape((dim ** 2))

            return funab

        # Initialize the ZWFS object
        zernike_sensor = zwfs.ZWFS(wavelength=self.wave, instrument=self.instrument)
        pup_dim = zernike_sensor.pupil_diameter
        # ZWFS calibration with clear image
        zernike_sensor.calibrate(output_path=self.output_path)
        # Reference OPD for differential measurement with flat DMs
        zernike_sensor.make_reference_opd(self.wave)

        # Initialize the frequencies to be tested
        # How many samples in each direction
        nb_freqx = 24
        nb_freqy = 1

        # Boundaries in cycles/pupil
        freqx_max = 7
        freqx_min = 1
        freqy_max = 0
        freqy_min = 0

        # Define frequencies to be probed
        freqx = np.linspace(freqx_min, freqx_max, nb_freqx)
        freqy = np.linspace(freqy_min, freqy_max, nb_freqy)

        # a and b amplitude to be tested. In nm.
        aamp = 0e-8
        bamp = 1e-8

        # Pupil as on the DM.
        dm_pup = zwfs.aperture.disc(34, 34, diameter=True)

        # Measured coefficients stack array
        ab_stack = np.zeros((nb_freqx, nb_freqy, 2))
        # DM shapes stack array
        shapes_stack = np.zeros((nb_freqx, nb_freqy, 34, 34))
        # Measured OPDs stack array
        zopd_stack = np.zeros((nb_freqx, nb_freqy, pup_dim, pup_dim))

        # Actual loop for Fourier measurements
        for i, fx in enumerate(freqx):
            for j, fy in enumerate(freqy):

                # Define the Fourier function for the set of frequencies fx,fy
                fourier_fun = fourier_ab(fx, fy)

                # Define & save the DM surface
                dm_shape = fourier_fun(dm_pup, aamp, bamp).reshape((34, 34))
                zernike_sensor.save_list(dm_shape, f'dmshape_x{fx:.2f}_y{fy:.2}', self.output_path+'/')
                shapes_stack[i, j] = dm_shape.copy()

                # Perform ZWFS measurement with sin on DM1
                zopd = zernike_sensor.perform_zwfs_measurement(self.wave,
                                                               output_path=self.output_path,
                                                               differential=True,
                                                               dm1_shape=dm_shape,
                                                               file_mode=True).squeeze()

                # Crop the computed OPD to keep the central part and save it
                array_dim = zopd.shape[-1]
                cropped_zopd = zopd[(array_dim - pup_dim) // 2:(array_dim + pup_dim) // 2,
                               (array_dim - pup_dim) // 2:(array_dim + pup_dim) // 2]
                fits.writeto(self.output_path + f'/zopd_x{fx:.2f}_y{fy:.2}.fits', cropped_zopd)

                # Store the cropped OPD
                zopd_stack[i, j] = cropped_zopd.copy()

                # Fit the introduced Fourier function to retrieve a and b coefficients
                final_roi = zwfs.aperture.disc(zernike_sensor.pupil_diameter, zernike_sensor.pupil_diameter,
                                               diameter=True)
                ab_fit, _ = so.curve_fit(fourier_fun, final_roi,
                                         cropped_zopd.reshape(zernike_sensor.pupil_diameter ** 2))

                # Store the measured coefficients
                ab_stack[i, j] = ab_fit  # / reference_fit * 1e-9


        # Plot the 1D curve results
        plt.figure(figsize=(20, 10))

        # Plot a and b response for x and y frequencies
        plt.semilogy(freqx, abs(ab_stack[:, 0, 1]), label='x; b_coeff')
        plt.semilogy(freqy, abs(ab_stack[0, :, 1]), label='y; b_coeff')
        plt.semilogy(freqx, abs(ab_stack[:, 0, 0]), label='x; a_coeff')
        plt.semilogy(freqy, abs(ab_stack[0, :, 0]), label='y; a_coeff')
        plt.legend()

        plt.xlabel('Spatial frequency (c/p)')
        plt.ylabel('Fitted coefficient')

        plt.savefig(self.output_path + '/frequency_plot.pdf')

        # Plot the 2D image results
        plt.figure(figsize=(10, 10))
        plt.imshow(np.flipud(abs(ab_stack[:, :, 0])), extent=[freqx_min, freqx_max, freqy_min, freqy_max])
        plt.savefig(self.output_path + '/2D_plot.pdf')

        np.save(self.output_path + '/dm_shapes', shapes_stack)
        np.save(self.output_path + '/numpy_ab_stack', ab_stack)



