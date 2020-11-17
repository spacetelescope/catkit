# noinspection PyUnresolvedReferences
import os.path
import astropy.io.fits as fits

from catkit.hardware.boston import commands
from hicat.hardware import testbed
from catkit.catkit_types import units, quantity, LyotStopPosition
from hicat.experiments.Experiment import Experiment
from hicat.experiments.ApplyActuatorPattern import ApplyCenterPokePlus, ApplyApodizerStrutsPoke, ApplyAsymmetricTestPattern
from hicat.experiments.modules import iris_ao
import hicat.util
from hicat.wfc_algorithms.wfsc_utils import take_pupilcam_hicat
from hicat.hardware.testbed import move_lyot_stop
from hicat.config import CONFIG_INI


class DMAlignmentData(Experiment):
    name = 'DM Alignment Data'

    def __init__(self, exptime_pupil=None, amplitudes = None, **kwargs):
        """ Take a set of calibration images for DM alignment

        :param exptime_pupil: flat, exptime in microsec. Set to None to
            use default value in take_pupilcam_hicat.
        """
        super().__init__(**kwargs)

        if amplitudes is None:
            amplitudes = (CONFIG_INI.getfloat('boston_kilo952', 'dm1_ideal_poke'),
                          CONFIG_INI.getfloat('boston_kilo952', 'dm2_ideal_poke'))

        self.exptime_pupil = exptime_pupil
        self.amplitudes = amplitudes

    def experiment(self):

        self.output_path = hicat.util.create_data_path(suffix=self.suffix)
        hicat.util.setup_hicat_logging(self.output_path, self.suffix)

        centerpokeplus_actuators = ApplyCenterPokePlus.actuators
        asymmetric_poke_actuators = ApplyAsymmetricTestPattern.actuators
        apodizer_struts_actuators = ApplyApodizerStrutsPoke.actuators

        zeroamp = quantity(0, units.nanometer)

        with testbed.laser_source() as laser, \
                testbed.dm_controller() as dm, \
                testbed.iris_ao() as iris_dm, \
                testbed.motor_controller() as motor_controller, \
                testbed.beam_dump() as beam_dump, \
                testbed.imaging_camera() as cam, \
                testbed.pupil_camera() as pupilcam:
            devices = {'laser': laser,
                       'dm': dm,
                       'iris_dm': iris_dm,
                       'motor_controller': motor_controller,
                       'beam_dump': beam_dump,
                       'imaging_camera': cam,
                       'pupil_camera': pupilcam}

            # Flatten the IrisAO
            self.devices['iris_dm'].apply_shape(iris_ao.flat_command())

            # Move Lyot stop out
            move_lyot_stop(LyotStopPosition.out_of_beam)

            # Take pupil image with both DMs flat, for reference
            flat_dm1 = commands.flat_command(bias=False, flat_map=True, dm_num=1)
            flat_dm2 = commands.flat_command(bias=False, flat_map=True, dm_num=2)
            dm.apply_shape_to_both(flat_dm1, flat_dm2)
            pupil_reference = take_pupilcam_hicat(devices, num_exposures=1, initial_path=self.output_path, suffix='pupilcam_dms_both_flat',
                                                 exposure_time=self.exptime_pupil)[0]
            fits.writeto(os.path.join(self.output_path, 'pupilcam_both_flat.fits'), pupil_reference)

            # Apply pattern to target DM, and zero to the other
            for amp in self.amplitudes:
                amplitude = quantity(amp, units.nanometer)
                for i, pattern in enumerate([centerpokeplus_actuators, asymmetric_poke_actuators, apodizer_struts_actuators]):

                    for dmnum in [1,2]:

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
                        pupil_image = take_pupilcam_hicat(devices, num_exposures=1, initial_path=self.output_path, suffix='pupilcam'+suffix,
                                            exposure_time=self.exptime_pupil)[0]

                        # Now do the subtraction of the reference (flat) pupil image from that pupil image
                        fits.writeto(os.path.join(self.output_path, 'pupilcam_delta{}.fits'.format(suffix)),
                                     pupil_image - pupil_reference)

            # Move Lyot stop in
            move_lyot_stop(LyotStopPosition.in_beam)

            # Update reference image
            dm.apply_shape_to_both(flat_dm1, flat_dm2)
            pupil_reference = take_pupilcam_hicat(devices, num_exposures=1, initial_path=self.output_path,
                                                  suffix='pupilcam_withlyot_dms_both_flat',
                                                  exposure_time=self.exptime_pupil)[0]
            fits.writeto(os.path.join(self.output_path, 'pupilcam_withlyot_both_flat.fits'), pupil_reference)


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

