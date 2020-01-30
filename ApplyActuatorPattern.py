import time

from catkit.catkit_types import units, quantity
from catkit.hardware.boston import commands
from hicat.config import CONFIG_INI
from hicat.experiments.Experiment import Experiment
from hicat.hardware import testbed


class ApplyActuatorPattern(Experiment):
    """
    Apply a DM map that is specified by a set of actuator numbers on one or both DMs.

    This class is supposed to be inherited by child classes that actually initialize with a list of actuators.
    apply_to_both: bool, if True, dm_num will be ignored and the actuator map will be applied to both DMs simultaneously
    dm_num: int, 1 or 2, which DM to apply the poke pattern to
    actuators: list of actuators that build the poke pattern. Note how you need to subtract add 1 to this list if you
                want to identify any given actuator on the actuator map provided by the manufacturer.
    """
    name = "Apply Actuator Pattern"
    suffix = "apply_actuator_pattern"

    def __init__(self, apply_to_both=False, dm_num=1, output_path=None):
        super().__init__(output_path=output_path, suffix=self.suffix)
        self.apply_to_both = apply_to_both
        if not apply_to_both:
            self.dm_num = dm_num

    def experiment(self):

        # Read ideal amplitude for poke patterns on the DMs
        dm1_poke_amplitude = CONFIG_INI.getfloat('boston_kilo952', 'dm1_ideal_poke')
        dm2_poke_amplitude = CONFIG_INI.getfloat('boston_kilo952', 'dm2_ideal_poke')

        if self.apply_to_both:
            dm_to_poke = 1
            poke_pattern = commands.poke_command(self.actuators, dm_num=dm_to_poke,
                                                 amplitude=quantity(dm1_poke_amplitude, units.nanometers))
            dm_to_flat = 2
            flat_pattern = commands.poke_command(self.actuators, dm_num=dm_to_flat,
                                                 amplitude=quantity(dm2_poke_amplitude, units.nanometers))

        else:
            dm_to_poke = self.dm_num
            dm_to_flat = 2 if self.dm_num == 1 else 1

            poke_amplitude = dm1_poke_amplitude if self.dm_num == 1 else dm2_poke_amplitude

            poke_pattern = commands.poke_command(self.actuators, dm_num=dm_to_poke,
                                                 amplitude=quantity(poke_amplitude, units.nanometers))
            flat_pattern = commands.flat_command(False, True, dm_num=dm_to_flat)

        with testbed.dm_controller() as dm:
            dm.apply_shape(poke_pattern, dm_num=dm_to_poke)
            dm.apply_shape(flat_pattern, dm_num=dm_to_flat)
            self.log.info("{} applied.".format(self.name))
            self.log.info(
                " ** This will loop forever, maintaining the {}. You must cancel the script to terminate it. ** ".format(self.name))
            self.log.info(
                " ** I.e. use square 'stop' button in PyCharm. Caution - be careful to single click, not double click it! ** ")

            while True:
                time.sleep(1)


class ApplyXPoke(ApplyActuatorPattern):
    """
    Apply a center-symmetric cross poke pattern on DM 1 or DM2, or both.

    apply_to_both: bool, if True, dm_num will be ignored and the actuator map will be applied to both DMs simultaneously
    dm_num: int, 1 or 2, which DM to apply the poke pattern to
    """
    name = "Apply X Poke"
    suffix = "apply_x_poke"
    actuators = [492, 525, 558, 591, 624, 657, 689, 720, 750, 779, 807, 833,  # top right cross beam
                 459, 426, 393, 360, 327, 294, 262, 231, 201, 172, 144, 118,  # bottom left cross beam
                 856, 828, 798, 767, 735, 702, 668, 633, 598, 563, 528, 493,  # top left cross beam
                 458, 423, 388, 353, 318, 283, 249, 216, 184, 153, 123, 95]  # bottom right cross beam


class ApplyCenterPoke(ApplyActuatorPattern):
    """
    Poke the four central actuators on DM 1 or DM2, or both.

    apply_to_both: bool, if True, dm_num will be ignored and the actuator map will be applied to both DMs simultaneously
    dm_num: int, 1 or 2, which DM to apply the poke pattern to
    """
    name = "Apply Center Poke"
    suffix = "apply_center_poke"
    actuators = [458, 459, 492, 493]


class ApplyCenterPokePlus(ApplyActuatorPattern):
    """
    Poke actuators in a pattern that includes the center poke and four other pokes aligned in a "plus"
    pattern which are visible through the apodizer pattern:
          []

    []    []    []

          []

    This is intended for DM1 to DM2 alignment, and apodizer to DM alignment.

    apply_to_both: bool, if True, dm_num will be ignored and the actuator map will be applied to both DMs simultaneously
    dm_num: int, 1 or 2, which DM to apply the poke pattern to
    """
    name = "Apply Center Poke Plus"
    suffix = "apply_center_poke_plus"
    actuators = [493, 492, 459, 458, 789, 788, 759, 758, 193, 192, 163, 162, 502, 501, 468, 467, 484, 483, 450, 449]


class ApplyOuterPoke(ApplyActuatorPattern):
    """
    Poke all edge actuators of one or both DMs.

    apply_to_both: bool, if True, dm_num will be ignored and the actuator map will be applied to both DMs simultaneously
    dm_num: int, 1 or 2, which DM to apply the poke pattern to
    """
    name = "Apply Outer Poke"
    suffix = "apply_outer_poke"
    actuators = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 26, 27, 46, 47, 69, 93, 119, 147, 177, 207, 239, 271,
                 305, 339, 373, 407, 441, 475, 509, 543, 577, 611, 645, 679, 711, 743, 773, 803, 831, 857,
                 881, 903, 923, 922, 939, 938, 951, 950, 949, 948, 947, 946, 945, 944, 943, 942, 941, 940,
                 925, 924, 905, 904, 882, 858, 832, 804, 774, 744, 712, 680, 646, 612, 578, 544, 510, 476,
                 442, 408, 374, 340, 306, 272, 240, 208, 178, 148, 120, 94, 70, 48, 28, 29, 12, 13]


class ApplyApodizerStrutsPoke(ApplyActuatorPattern):
    """
    Poke actuators behind the apodizer struts on one or both DMs.

    apply_to_both: bool, if True, dm_num will be ignored and the actuator map will be applied to both DMs simultaneously
    dm_num: int, 1 or 2, which DM to apply the poke pattern to
    """
    name = "Apply Actuator Strut Poke"
    suffix = "apply_actuator_strut_poke"
    actuators = [699, 631, 562, 763, 823,  # top left
                 559, 626, 692, 754, 812,  # top right
                 392, 325, 259, 197, 139,  # bottom left
                 389, 320, 252, 188, 128]  # bottom right