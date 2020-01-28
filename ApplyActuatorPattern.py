import time

from catkit.hardware.boston import commands
from hicat.hardware import testbed
from catkit.catkit_types import units, quantity
from hicat.experiments.Experiment import Experiment


class ApplyActuatorPattern(Experiment):
    """
    Apply a DM map that is specified by a set of actuator numbers.
    """
    name = "Apply Actuator Pattern"

    def __init__(self, apply_to_both=False, dm_num=1, output_path=None, suffix='apply_actuator_pattern', actuators=None):
        super().__init__(output_path=output_path, suffix=suffix)
        self.apply_to_both = apply_to_both
        if apply_to_both:
            self.dm_num = dm_num
        self.actuators = actuators  # list of actuators

    def experiment(self):
        if self.apply_to_both:
            dm_to_poke = 1
            poke_pattern = commands.poke_command(self.actuators, dm_num=dm_to_poke,
                                                 amplitude=quantity(200, units.nanometers))
            dm_to_flat = 2
            flat_pattern = commands.poke_command(self.actuators, dm_num=dm_to_poke,
                                                 amplitude=quantity(-150, units.nanometers))

        else:
            dm_to_poke = self.dm_num
            dm_to_flat = 2 if self.dm_num == 1 else 1

            poke_amplitude = 200 if self.dm_num == 1 else -150

            poke_pattern = commands.poke_command(self.actuators, dm_num=dm_to_poke,
                                                 amplitude=quantity(poke_amplitude, units.nanometers))
            flat_pattern = commands.flat_command(False, True, dm_num=dm_to_flat)

        with testbed.dm_controller() as dm:
            dm.apply_shape(poke_pattern, dm_num=dm_to_poke)
            dm.apply_shape(flat_pattern, dm_num=dm_to_flat)
            self.log.info("{} applied.".format(self.suffix))
            self.log.info(
                " ** This will loop forever, maintaining the {}. You must cancel the script to terminate it. ** ".format(self.suffix))
            self.log.info(
                " ** I.e. use square 'stop' button in PyCharm. Caution - be careful to single click, not double click it! ** ")

            while True:
                time.sleep(1)
