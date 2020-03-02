# noinspection PyUnresolvedReferences
import os.path
import astropy.io.fits as fits

from catkit.hardware.boston import commands
from hicat.hardware import testbed
from catkit.catkit_types import units, quantity, LyotStopPosition
from hicat.experiments.Experiment import Experiment
import hicat.util
from hicat.wfc_algorithms.stroke_min import take_pupilcam_hicat
from hicat.hardware.testbed import move_lyot_stop


class DMAlignmentData(Experiment):
    name = 'DM Alignment Data'

    def __init__(self, exptime_pupil=None, **kwargs):
        """ Take a set of calibration images for DM alignment

        :param exptime_pupil: flat, exptime in microsec. Set to None to
            use default value in take_pupilcam_hicat.
        """
        super().__init__(**kwargs)

        self.exptime_pupil = exptime_pupil

    def experiment(self):

        self.output_path = hicat.util.create_data_path(suffix=self.suffix)
        hicat.util.setup_hicat_logging(self.output_path, self.suffix)

        centerpokeplus_actuators = [493, 492, 459, 458, 789, 788, 759, 758, 193, 192, 163, 162, 502, 501, 468, 467, 484, 483, 450, 449]

        asymmetric_poke_actuators = [493, 492, 459, 458, 789, 788, 759, 758, 193, 192, 163, 162, 502, 501, 468, 467, 728, 727, 696, 695,
             663, 662, 818, 817, 770, 769, 768, 767, 766, 737, 736, 735, 738, 739 ]

        apodizer_struts_actuators = [699, 631, 562, 763, 823,   # top left
                                     559, 626, 692, 754, 812,   # top right
                                     392, 325, 259, 197, 139,   # bottom left
                                     389, 320, 252, 188, 128]   # bottom right

        zeroamp = quantity(0, units.nanometers)

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

            # Take pupil image with both DMs flat, for reference
            flat_dm1 = commands.flat_command(bias=False, flat_map=True, dm_num=1)
            flat_dm2 = commands.flat_command(bias=False, flat_map=True, dm_num=2)
            dm.apply_shape_to_both(flat_dm1, flat_dm2)
            pupil_filenames = take_pupilcam_hicat(devices, initial_path=self.output_path, suffix='pupilcam_dms_both_flat',
                                                 exposure_time=self.exptime_pupil)
            pupil_reference = fits.getdata(pupil_filenames[0])
            fits.writeto(os.path.join(self.output_path, 'pupilcam_both_flat.fits'), pupil_reference)

            # Apply pattern to target DM, and zero to the other
            for amp in [100, 500, -300]:
                amplitude = quantity(amp, units.nanometers)
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
                        pupil_filenames = take_pupilcam_hicat(devices, initial_path=self.output_path, suffix='pupilcam'+suffix,
                                            exposure_time=self.exptime_pupil)
                        pupil_image = fits.getdata(pupil_filenames[0])

                        # Now do the subtraction of the reference (flat) pupil image from that pupil image
                        fits.writeto(os.path.join(self.output_path, 'pupilcam_delta{}.fits'.format(suffix)),
                                     pupil_image - pupil_reference)
