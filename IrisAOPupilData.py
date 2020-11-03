# noinspection PyUnresolvedReferences
import os.path
import astropy.io.fits as fits

from catkit.hardware.boston import commands
from catkit.hardware.iris_ao import segmented_dm_command
from catkit.catkit_types import units, quantity, LyotStopPosition
from hicat.experiments.ApplyActuatorPattern import ApplyAsymmetricTestPattern
from hicat.experiments.Experiment import Experiment
from hicat.experiments.modules import iris_ao
from hicat.hardware import testbed
from hicat.hardware.testbed import move_fpm, move_lyot_stop
import hicat.util
from hicat.wfc_algorithms.wfsc_utils import take_pupilcam_hicat
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
            # Move FPM in
            move_fpm('coron')

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

                # Define the letter F commands for IrisAO
                letter_f, letter_string = iris_ao.letter_f(self.dm_config_id, self.testbed_config_id,
                                                           self.iris_filename_flat, self.iris_wavelength)

                # Apply letter F shape to IrisAO while Bostons are still flat
                letter_f_command = segmented_dm_command.load_command(letter_f, self.dm_config_id,
                                                                     self.iris_wavelength, self.testbed_config_id,
                                                                     apply_flat_map=True,
                                                                     filename_flat=self.iris_filename_flat)

                iris_dm.apply_shape(letter_f_command)

                # Take pupil exposure.
                suffix = f'Bostons_flat_IrisAO_{letter_string}'
                pupil_image1 = take_pupilcam_hicat(devices, num_exposures=1, initial_path=self.output_path, suffix=f'pupilcam_{suffix}',
                                                   exposure_time=self.exptime_pupil)[0]

                # Now do the subtraction of the reference (flat) pupil image from that pupil image
                fits.writeto(os.path.join(self.output_path, f'pupilcam_delta_{suffix}.fits'),
                             pupil_image1 - pupil_reference)

                # Apply asymmetric pattern do DM1, keep letter F on IrisAO
                asymmetric_poke_actuators = ApplyAsymmetricTestPattern.actuators
                amp = CONFIG_INI.getfloat('boston_kilo952', 'dm1_ideal_poke')
                amplitude = quantity(amp, units.nanometer)
                command_dm1 = commands.poke_command(asymmetric_poke_actuators, dm_num=1, amplitude=amplitude)
                dm.apply_shape(command_dm1, dm_num=1)

                # Take pupil exposure.
                suffix = f'DM1_asymmetric_IrisAO_{letter_string}'
                pupil_image2 = take_pupilcam_hicat(devices, num_exposures=1, initial_path=self.output_path, suffix=f'pupilcam_{suffix}',
                                                   exposure_time=self.exptime_pupil)[0]

                # Now do the subtraction of the reference (flat) pupil image from that pupil image
                fits.writeto(os.path.join(self.output_path, f'pupilcam_delta_{suffix}.fits'),
                             pupil_image2 - pupil_reference)
