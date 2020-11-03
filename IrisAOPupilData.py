# noinspection PyUnresolvedReferences
import os.path
import astropy.io.fits as fits
import numpy as np

from catkit.hardware.boston import commands
from catkit.hardware.iris_ao import segmented_dm_command
from catkit.catkit_types import units, quantity, LyotStopPosition
from hicat.experiments.Experiment import Experiment
from hicat.experiments.modules import iris_ao
from hicat.hardware import testbed
from hicat.hardware.testbed import move_lyot_stop
import hicat.util
from hicat.wfc_algorithms.wfsc_utils import take_exposure_hicat, take_pupilcam_hicat
from hicat.config import CONFIG_INI


class IrisAOPupilData(Experiment):
    name = 'IrisAO Pupil Data'

    def __init__(self, exptime_pupil=None, **kwargs):
        """ Take a set of calibration pupil images for IrisAO calibration.

        :param exptime_pupil: flat, exptime in microsec. Set to None to
               use default value in take_pupilcam_hicat.
        """
        super().__init__(**kwargs)

        self.exptime_pupil = exptime_pupil

        self.testbed_config_id = 'testbed'
        self.dm_config_id = CONFIG_INI.get(self.testbed_config_id, 'iris_ao')
        self.iris_wavelength = CONFIG_INI.getfloat('thorlabs_source_mcls1', 'lambda_nm')
        repo_root = hicat.util.find_repo_location()
        self.iris_filename_flat = os.path.join(repo_root, CONFIG_INI.get(self.dm_config_id, 'custom_flat_file_ini'))

    def experiment(self):

        self.output_path = hicat.util.create_data_path(suffix=self.suffix)

        with testbed.laser_source() as laser, \
                testbed.dm_controller() as dm, \
                testbed.motor_controller() as motor_controller, \
                testbed.beam_dump() as beam_dump, \
                testbed.imaging_camera() as cam, \
                testbed.pupil_camera() as pupilcam:
            devices = {'laser': laser,
                       'dm': dm,
                       'motor_controller': motor_controller,
                       'beam_dump': beam_dump,
                       'imaging_camera': cam,
                       'pupil_camera': pupilcam}

            # Move Lyot stop out
            move_lyot_stop(LyotStopPosition.out_of_beam)

            with testbed.iris_ao(self.dm_config_id) as iris_dm:

                # Take pupil image with all three DMs flat, for reference
                flat_dm1 = commands.flat_command(bias=False, flat_map=True, dm_num=1)
                flat_dm2 = commands.flat_command(bias=False, flat_map=True, dm_num=2)
                flat_irisao = segmented_dm_command.load_command(iris_ao.zero_array(nseg=37)[0], self.dm_config_id, self.iris_wavelength,
                                                                self.testbed_config_id, apply_flat_map=True,
                                                                filename_flat=self.iris_filename_flat)

                dm.apply_shape_to_both(flat_dm1, flat_dm2)
                iris_dm.apply_shape(flat_irisao)

                # Take pupil image
                pupil_reference = take_pupilcam_hicat(devices, num_exposures=1, initial_path=self.output_path, suffix='pupilcam_dms_all_flat',
                                                      exposure_time=self.exptime_pupil)[0]
                fits.writeto(os.path.join(self.output_path, 'pupilcam_all_flat.fits'), pupil_reference)

                # Take focal plane direct image
                direct_reference, direct_header = take_exposure_hicat(np.zeros(952), np.zeros(952), devices,
                                                                      wavelength=self.iris_wavelength,
                                                                      exposure_type='direct',
                                                                      exposure_time=None,
                                                                      auto_expose=True,
                                                                      initial_path=self.output_path,
                                                                      num_exposures=5,
                                                                      file_mode=True,
                                                                      suffix=f"direct",
                                                                      raw_skip=np.inf)

                # Define the commands that should be run
                zero_array, zero_string = iris_ao.zero_array(nseg=37)
                letter_f, letter_string = iris_ao.letter_f(self.dm_config_id, self.testbed_config_id,
                                                           self.iris_filename_flat, self.iris_wavelength)

                # Apply pattern to IrisAO and take pupil images
                for i, pattern in enumerate([(zero_array, zero_string), (letter_f, letter_string)]):

                    # Apply shape to IrisAO
                    iris_command = segmented_dm_command.load_command(pattern[0], self.dm_config_id,
                                                                     self.iris_wavelength, self.testbed_config_id,
                                                                     apply_flat_map=True,
                                                                     filename_flat=self.iris_filename_flat)

                    iris_dm.apply_shape(iris_command)

                    # Take pupil exposure.
                    suffix = f'_pattern{i}_{pattern[1]}'
                    pupil_image = take_pupilcam_hicat(devices, num_exposures=1, initial_path=self.output_path, suffix=f'pupilcam{suffix}',
                                                      exposure_time=self.exptime_pupil)[0]

                    # Now do the subtraction of the reference (flat) pupil image from that pupil image
                    fits.writeto(os.path.join(self.output_path, 'pupilcam_delta{}.fits'.format(suffix)),
                                 pupil_image - pupil_reference)

                    # Take focal plane direct image
                    direct_reference, direct_header = take_exposure_hicat(np.zeros(952), np.zeros(952), devices,
                                                                          wavelength=self.iris_wavelength,
                                                                          exposure_type='direct',
                                                                          exposure_time=None,
                                                                          auto_expose=True,
                                                                          initial_path=self.output_path,
                                                                          num_exposures=5,
                                                                          file_mode=True,
                                                                          suffix=f"direct{suffix}",
                                                                          raw_skip=np.inf)
                """
                # Move Lyot stop in
                move_lyot_stop(LyotStopPosition.in_beam)

                # Update reference image
                dm.apply_shape_to_both(flat_dm1, flat_dm2)
                pupil_reference = take_pupilcam_hicat(devices, num_exposures=1, initial_path=self.output_path,
                                                      suffix='pupilcam_withlyot_dms_all_flat',
                                                      exposure_time=self.exptime_pupil)[0]
                fits.writeto(os.path.join(self.output_path, 'pupilcam_withlyot_all_flat.fits'), pupil_reference)


                for amp in self.amplitudes:
                    amplitude = quantity(amp, units.nanometer)
                    for i, pattern in enumerate([centerpokeplus_actuators, apodizer_struts_actuators]):

                        for dmnum in [1]:

                            # Apply shapes to DMs
                            if dmnum==1:
                                command_dm1 = commands.poke_command(pattern, dm_num=1, amplitude=amplitude)
                                command_dm2 = commands.poke_command(pattern, dm_num=2, amplitude=zeroamp)
                            else:
                                command_dm1 = commands.poke_command(pattern, dm_num=1, amplitude=zeroamp)
                                command_dm2 = commands.poke_command(pattern, dm_num=2, amplitude=amplitude)

                            dm.apply_shape_to_both(command_dm1, command_dm2)

                            # Take pupil exposure.
                            suffix = '_pattern{}_dm{}_amp{}'.format(i,dmnum,amp)
                            pupil_image = take_pupilcam_hicat(devices, num_exposures=1, initial_path=self.output_path, suffix='pupilcam_withlyot_'+suffix,
                                                exposure_time=self.exptime_pupil)[0]

                            # Now do the subtraction of the reference (flat) pupil image from that pupil image
                            fits.writeto(os.path.join(self.output_path, 'pupilcam_withlyot_delta{}.fits'.format(suffix)),
                                         pupil_image - pupil_reference)
                    """