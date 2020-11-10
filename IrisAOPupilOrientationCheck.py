# noinspection PyUnresolvedReferences
import os.path
import astropy.io.fits as fits

from catkit.hardware.boston import commands
from catkit.catkit_types import units, quantity, LyotStopPosition
from hicat.experiments.ApplyActuatorPattern import ApplyAsymmetricTestPattern
from hicat.experiments.Experiment import Experiment
from hicat.experiments.modules import iris_ao
from hicat.hardware import testbed
from hicat.hardware.testbed import move_fpm, move_lyot_stop
import hicat.util
from hicat.wfc_algorithms.wfsc_utils import take_pupilcam_hicat
from hicat.config import CONFIG_INI


class IrisAOPupilOrientationCheck(Experiment):
    name = 'IrisAO Pupil Data'

    def __init__(self, exptime_pupil=None, **kwargs):
        """ Take a set of calibration pupil images for IrisAO calibration.

        :param exptime_pupil: float, exptime in microsec. Set to None to
               use default value in take_pupilcam_hicat.
        """
        super().__init__(**kwargs)

        self.exptime_pupil = exptime_pupil

    def experiment(self):

        self.output_path = hicat.util.create_data_path(suffix=self.suffix)

        with testbed.dm_controller() as dm, \
             testbed.motor_controller() as motor_controller, \
             testbed.beam_dump() as beam_dump, \
             testbed.imaging_camera() as cam, \
             testbed.pupil_camera() as pupilcam:
            devices = {'dm': dm,
                       'motor_controller': motor_controller,
                       'beam_dump': beam_dump,
                       'imaging_camera': cam,
                       'pupil_camera': pupilcam}

            # Move Lyot stop out
            move_lyot_stop(LyotStopPosition.out_of_beam)
            # Move FPM in
            move_fpm('coron')

            with testbed.iris_ao() as iris_dm:

                # Take pupil image with all three DMs flat, for reference
                flat_dm1 = commands.flat_command(bias=False, flat_map=True, dm_num=1)
                flat_dm2 = commands.flat_command(bias=False, flat_map=True, dm_num=2)
                flat_irisao = iris_ao.flat_command()

                dm.apply_shape_to_both(flat_dm1, flat_dm2)
                iris_dm.apply_shape(flat_irisao)

                # Take pupil image
                pupil_reference = take_pupilcam_hicat(devices, num_exposures=1, initial_path=self.output_path, suffix='pupilcam_dms_all_flat',
                                                      exposure_time=self.exptime_pupil)[0]
                fits.writeto(os.path.join(self.output_path, 'pupilcam_all_flat.fits'), pupil_reference)

                # Apply letter F shape to IrisAO while Bostons are still flat
                letter_f_command = iris_ao.letter_f()
                iris_dm.apply_shape(letter_f_command)

                # Take pupil exposure.
                suffix = f'Bostons_flat_IrisAO_letter_F'
                pupil_image1 = take_pupilcam_hicat(devices, num_exposures=1, initial_path=self.output_path, suffix=f'pupilcam_{suffix}',
                                                   exposure_time=self.exptime_pupil)[0]

                # Now do the subtraction of the reference (flat) pupil image from that pupil image
                fits.writeto(os.path.join(self.output_path, f'pupilcam_delta_{suffix}.fits'),
                             pupil_image1 - pupil_reference)

                # Apply asymmetric pattern to DM1, keep letter F on IrisAO
                asymmetric_poke_actuators = ApplyAsymmetricTestPattern.actuators
                amp = CONFIG_INI.getfloat('boston_kilo952', 'dm1_ideal_poke')
                amplitude = quantity(amp, units.nanometer)
                command_dm1 = commands.poke_command(asymmetric_poke_actuators, dm_num=1, amplitude=amplitude)
                dm.apply_shape(command_dm1, dm_num=1)

                # Take pupil exposure.
                suffix = f'DM1_asymmetric_IrisAO_letter_F'
                pupil_image2 = take_pupilcam_hicat(devices, num_exposures=1, initial_path=self.output_path, suffix=f'pupilcam_{suffix}',
                                                   exposure_time=self.exptime_pupil)[0]

                # Now do the subtraction of the reference (flat) pupil image from that pupil image
                fits.writeto(os.path.join(self.output_path, f'pupilcam_delta_{suffix}.fits'),
                             pupil_image2 - pupil_reference)
