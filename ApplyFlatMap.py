import logging
import time

from hicat.experiments.Experiment import Experiment
from catkit.hardware.boston.commands import flat_command
from hicat.hardware import testbed


class ApplyFlatMap(Experiment):
    name = "Apply Flat Map"
    log = logging.getLogger(__name__)

    def __init__(self,
                 dm1_command_object=flat_command(bias=False, flat_map=True),  # Default flat with bias.
                 dm2_command_object=flat_command(bias=False, flat_map=True),  # Default flat with bias.
                 output_path=None,
                 suffix='apply_flat_map',
                 **kwargs
                 ):
        """
        Takes a set of data with any camera, any DM command, any exposure time, etc.
        :param dm1_command_object: (DmCommand) DmCommand object to apply on DM1.
        :param dm1_command_object: (DmCommand) DmCommand object to apply on DM2.

        """
        super(ApplyFlatMap, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.dm1_command_object = dm1_command_object
        self.dm2_command_object = dm2_command_object

    def experiment(self):
        with testbed.dm_controller() as dm:
            dm.apply_shape_to_both(self.dm1_command_object, self.dm2_command_object)
            self.log.info("Flat Map applied.")
            self.log.info(" ** This will loop forever, maintaining the flat map. You must cancel the script to terminate it. ** ")
            self.log.info(" ** I.e. use square 'stop' button in PyCharm. Caution - be careful to single click, not double click it! ** ")

            while True:
                time.sleep(1)
