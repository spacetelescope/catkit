# flake8: noqa: E402
import itertools
import os

from catkit.catkit_types import quantity, units, SinSpecification, FpmPosition, LyotStopPosition, \
    ImageCentering  # noqa: E402
from catkit.hardware.boston.sin_command import sin_command  # noqa: E402
from catkit.hardware.boston.commands import flat_command
from hicat.experiments.Experiment import Experiment  # noqa: E402
from hicat.hardware import testbed  # noqa: E402
import hicat.util  # noqa: E402


class CalibrateDMRotation(Experiment):
    """ Measure DM rotation angles relative to focal plane detector axes.

    :param cycles: range, cycles per aperture (spatial frequency) in lambda/D
    :param orientation_angles: list, rotation angles for the sine wave in degrees
    :param phase_shifts: list, phase between DM patterns in degrees - affects relative brightness of resulting speckles
    """
    name = 'Calibrate DM Rotation'
    def __init__(self, cycles=16, amplitude=50):
        super().__init__()
        self.cycles = cycles
        self.amplitude=amplitude


    def take_image(self, label):
        # Take images
        saveto_path = hicat.util.create_data_path(initial_path=self.output_path,
                                                  suffix=label)
        return testbed.run_hicat_imaging(exposure_time=quantity(50, units.millisecond),
                                  num_exposures=1,
                                  fpm_position=FpmPosition.coron,
                                  lyot_stop_position=LyotStopPosition.in_beam,
                                  file_mode=True,
                                  raw_skip=False,
                                  path=saveto_path,
                                  auto_exposure_time=False,
                                  exposure_set_name='coron',
                                  centering=ImageCentering.custom_apodizer_spots,
                                  auto_exposure_mask_size=5.5,
                                  resume=False,
                                  pipeline=True)

    def experiment(self):

        with testbed.dm_controller() as dm:

            # Take baseline image with DMs flat
            dm.apply_shape_to_both(flat_command(bias=False, flat_map=True), flat_command(bias=False, flat_map=True))
            baseline_im = self.take_image("both_dms_flat")

            # Apply sines
            for dm_sin in [1, 2]:
                dm_flat = 2 if dm_sin == 1 else 1
                for angle in [0,90]:
                    self.log.info(f"Taking sine wave on DM{dm_sin} at angle {angle} with {self.cycles} cycles/DM.")
                    sin_specification = SinSpecification(angle, self.cycles,
                                                               quantity(self.amplitude, units.nanometer), 0)
                    sin_command_object = sin_command(sin_specification, flat_map=True, dm_num=dm_sin)
                    flat_command_object = flat_command(bias=False, flat_map=True, dm_num=dm_flat)

                    dm.apply_shape(sin_command_object, dm_num=dm_sin)
                    dm.apply_shape(flat_command_object, dm_num=dm_flat)

                    label = f"dm{dm_sin}_cycle_{self.cycles}_ang_{angle}"

                    self.take_image(label)

                # Subtract off the baseline images and save the output differece image
