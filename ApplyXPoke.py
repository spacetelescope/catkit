import time

from catkit.hardware.boston import commands
from hicat.hardware import testbed
from catkit.catkit_types import units, quantity
from hicat.experiments.Experiment import Experiment


class ApplyXPoke(Experiment):
    """
    Apply a center-symmetric cross poke pattern on DM 1 or DM2
    """
    name = "Apply X Poke"

    def __init__(self, dm_num=1, output_path=None, suffix='apply_x_poke'):
        super().__init__(output_path=output_path, suffix=suffix)
        self.dm_num = dm_num
        self.actuators = [492, 525, 558, 591, 624, 657, 689, 720, 750, 779, 807, 833,  # top right cross beam
                          459, 426, 393, 360, 327, 294, 262, 231, 201, 172, 144, 118,  # bottom left cross beam
                          856, 828, 798, 767, 735, 702, 668, 633, 598, 563, 528, 493,  # top left cross beam
                          458, 423, 388, 353, 318, 283, 249, 216, 184, 153, 123, 95]  # bottom right cross beam

    def experiment(self):
        dm_to_poke = self.dm_num
        dm_to_flat = 2 if self.dm_num == 1 else 1

        poke_amplitude = 200 if self.dm_num == 1 else -150

        poke_pattern = commands.poke_command(self.actuators, dm_num=dm_to_poke,
                                             amplitude=quantity(poke_amplitude, units.nanometers))
        flat_pattern = commands.flat_command(False, True, dm_num=dm_to_flat)

        with testbed.dm_controller() as dm:
            dm.apply_shape(poke_pattern, dm_num=dm_to_poke)
            dm.apply_shape(flat_pattern, dm_num=dm_to_flat)
            self.log.info("X poke applied.")
            self.log.info(
                " ** This will loop forever, maintaining the X poke. You must cancel the script to terminate it. ** ")
            self.log.info(
                " ** I.e. use square 'stop' button in PyCharm. Caution - be careful to single click, not double click it! ** ")

            while True:
                time.sleep(1)
