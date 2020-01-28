import time

from catkit.hardware.boston import commands
from hicat.hardware import testbed
from catkit.catkit_types import units, quantity
from hicat.experiments.ApplyActuatorPattern import ApplyActuatorPattern


class ApplyXPoke(ApplyActuatorPattern):
    """
    Apply a center-symmetric cross poke pattern on DM 1 or DM2, or both.
    """
    name = "Apply X Poke"

    def __init__(self, apply_to_both=False, dm_num=1, output_path=None, suffix='apply_x_poke'):
        self.actuators = [492, 525, 558, 591, 624, 657, 689, 720, 750, 779, 807, 833,  # top right cross beam
                          459, 426, 393, 360, 327, 294, 262, 231, 201, 172, 144, 118,  # bottom left cross beam
                          856, 828, 798, 767, 735, 702, 668, 633, 598, 563, 528, 493,  # top left cross beam
                          458, 423, 388, 353, 318, 283, 249, 216, 184, 153, 123, 95]  # bottom right cross beam
        super().__init__(apply_to_both=apply_to_both, dm_num=dm_num, output_path=output_path, suffix=suffix, actuators=self.actuators)
