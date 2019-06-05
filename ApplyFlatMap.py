from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import logging
import time

from .Experiment import Experiment
from ..hardware.boston.commands import flat_command
from ..hardware import testbed


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
        super(ApplyFlatMap, self).__init__(output_path=output_path, suffix=suffix, no_output_dir=True, **kwargs)
        self.dm1_command_object = dm1_command_object
        self.dm2_command_object = dm2_command_object

    def experiment(self):
        with testbed.dm_controller() as dm:
            dm.apply_shape_to_both(self.dm1_command_object, self.dm2_command_object)
            self.log.info("Flat Map applied.")
            self.log.info(" ** This will loop forever, maintaining the flat map. You must cancel the script to terminate it. ** ")
            while True:
                time.sleep(1)
