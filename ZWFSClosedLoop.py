from hicat.experiments.Experiment import HicatExperiment
from hicat.control import zwfs
from hicat.wfc_algorithms import wfsc_utils
from hicat.hardware import testbed_state
from catkit.hardware.boston import DmCommand
import logging

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as cl
from astropy.io import fits

class ZWFSClosedLoop(HicatExperiment):
    name = "Run ZWFS closed loop test"
    log = logging.getLogger(__name__)

    def __init__(self,
                 instrument='HiCAT',
                 wave=640e-9,
                 filename='ZWFS',
                 align_lyot_stop=False,
                 run_ta=True):
        """
        Performs phase corrections in closed loop between ZWFS and DM1, to correct for an initial aberration
        introduced at the beginning of the loop.
        WARNING: Work in progress, not fully working !!!

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


        # Initialize values

        nb_iterations = 10
        num_zernike_mode = 4 # Number of the intial zernike. Here astig
        ab_rms_val = 4e-8 # value in nm RMS of the initial aberration
        gain = 1
        dm_pup = zwfs.aperture.disc(34,32,diameter=True, cpix=False)
        nm_to_m = 1e-9

        # Load reference DM shapes the algorithm will try to retrieve
        # ---------------------------------

        if testbed_state.simulation:
            # WARNING: local path
            shapes_path = '/mnt/c/Users/rpourcelot/Documents/git_repos/CLC2_dm_shapes/'
        else:
            shapes_path = 'C:/Users/HICAT/hicat_data/2020-09-18T15-01-14_broadband_stroke_minimization/iter0022/coron_640/dm_command'

        dm1_surf = fits.getdata(shapes_path+'dm1_command_2d_noflat.fits')
        dm2_surf = fits.getdata(shapes_path+'dm2_command_2d_noflat.fits')

        # Create DM commands
        dm1_command = DmCommand.DmCommand(dm1_surf, flat_map=True, bias=False, dm_num=1)
        dm2_command = DmCommand.DmCommand(dm2_surf, flat_map=True, bias=False, dm_num=2)


        # Initialize, calibrate and take reference OPD with Zernike sensor, DMs with reference shapes
        # ----------------------------------

        zernike_sensor = zwfs.ZWFS(wavelength=self.wave, instrument=self.instrument)
        zernike_sensor.calibrate(dm1_shape=dm1_command, dm2_shape=dm2_command,
                                 output_path=self.output_path)
        zernike_sensor.make_reference_opd(self.wave, dm1_shape=dm1_command, dm2_shape=dm2_command)

        pup_dim = zernike_sensor.pupil_diameter

        # Acquire non-aberrated data
        # --------------------------

        zernike_sensor.save_list(dm1_surf, 'initial_DM1_surf_it', self.output_path)

        dm1_vector = wfsc_utils.dm_actuators_from_surface(dm1_surf)
        dm2_vector = wfsc_utils.dm_actuators_from_surface(dm2_surf)

        # Take science image
        sc_img, _ = wfsc_utils.take_exposure_hicat(dm1_vector / nm_to_m,
                                                   dm2_vector / nm_to_m,
                                                   zernike_sensor.devices,
                                                   exposure_type='coron',
                                                   num_exposures=20,
                                                   exposure_time=5e5,
                                                   auto_expose=False,
                                                   initial_path=self.output_path,
                                                   suffix=f'ref_dh',
                                                   wavelength=self.wave * 1e9)

        dim = int(np.sqrt(sc_img.shape))
        sc_img = sc_img.reshape((dim, dim))

        zernike_sensor.save_list(zernike_sensor._reference_opd, 'reference_opd', self.output_path)
        zernike_sensor.save_list(sc_img, 'ref_DH', self.output_path)

        # Define initial aberration
        # -------------------------

        dm_zernike_basis = np.nan_to_num(zwfs.ztools.zernike.zernike_basis(npix=34, nterms=10))
        initial_aberration = dm_zernike_basis[num_zernike_mode] * ab_rms_val

        # Init the loop
        # current_dm_surf is the tracker of DM1 shape
        current_dm_surf = dm1_surf + initial_aberration

        # Stack for azimutal DH averages
        azimutal_mean_stack = []

        # Init figure for nice plots
        plt.figure(figsize=(40, 16))

        # Correction loop
        for it in range(nb_iterations):

            # Save DM1 surf & create DM command
            zernike_sensor.save_list(current_dm_surf, f'DM_surf_it{it}', self.output_path)
            dm1_command = DmCommand.DmCommand(current_dm_surf, flat_map=True, bias=False, dm_num=1)

            # Phase measurement
            zopd = zernike_sensor.perform_zwfs_measurement(self.wave, self.output_path,
                                                           differential=True,
                                                           dm1_shape=dm1_command,
                                                           dm2_shape=dm2_command)

            dm1_vector = wfsc_utils.dm_actuators_from_surface(current_dm_surf)
            dm2_vector = wfsc_utils.dm_actuators_from_surface(dm2_surf)

            # Take science image

            sc_img, _ = wfsc_utils.take_exposure_hicat(dm1_vector/nm_to_m,
                                                       dm2_vector/nm_to_m,
                                                       zernike_sensor.devices,
                                                       exposure_type='coron',
                                                       num_exposures=20,
                                                       exposure_time=5e5,
                                                       auto_expose=False,
                                                       initial_path=self.output_path,
                                                       suffix=f'iteration{it}',
                                                       wavelength=self.wave*1e9)
            
            dim = int(np.sqrt(sc_img.shape))
            sc_img = sc_img.reshape((dim,dim))

            # Crop measured OPD
            array_dim = zopd.shape[-1]
            cropped_zopd = zopd[(array_dim - pup_dim) // 2:(array_dim + pup_dim) // 2,
                               (array_dim - pup_dim) // 2:(array_dim + pup_dim) // 2]

            zernike_sensor.save_list(cropped_zopd, f'ZWFS_OPD_it{it}', self.output_path)

            # Resize and scale to match DM size
            sized_zopd = nm_to_m * gain * zwfs.imutils.scale(cropped_zopd, 0, new_dim=[34,34])

            # Store current dm surf for plotting
            dm_surf_backup = current_dm_surf.copy()

            # Update current surf.
            # Sign + instead of - takes into account the observed sign change in DM commands vs DM surfaces
            current_dm_surf = current_dm_surf + sized_zopd

            # Plotting section. Not finalized yet.
            plt.subplot(4, nb_iterations, it+1)
            plt.imshow(cropped_zopd, vmin=-40, vmax=40)
            plt.colorbar()
            plt.axis('off')

            plt.subplot(4, nb_iterations, nb_iterations+it+1)
            plt.imshow(dm_pup*dm_surf_backup-dm1_surf, vmin=-2e-8, vmax=2e-8)
            plt.axis('off')
            plt.colorbar()


            plt.subplot(4, nb_iterations, 2*nb_iterations+it+1)
            plt.imshow(abs(sc_img), norm=cl.LogNorm(vmin=1e-4))
            plt.colorbar()
            plt.axis('off')

            plt.subplot(4, nb_iterations, 3*nb_iterations+it+1)
            prof, x_sep = zwfs.imutils.profile(sc_img)
            azimutal_mean_stack.append(prof)

            for i in azimutal_mean_stack:
                plt.semilogy(x_sep, i)


        plt.tight_layout()

        # Save the figures.
        plt.savefig(self.output_path+'/final_plot.png')
        plt.savefig(self.output_path + '/final_plot.pdf')
