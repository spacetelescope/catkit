import logging
import time

from hicat.experiments.Experiment import Experiment
from hicat.experiments.modules import iris_ao
from catkit.hardware.boston.commands import flat_command
from hicat.hardware import testbed


class ApplyFlatMaps(Experiment):
    name = "Apply Flat Maps"
    log = logging.getLogger(__name__)

    def __init__(self,
                 dm1_command_object=flat_command(bias=False, flat_map=True),  # Default flat with bias.
                 dm2_command_object=flat_command(bias=False, flat_map=True),  # Default flat with bias.
                 iris_ao_command_object=iris_ao.flat_command(),  # Default custom flat map.
                 output_path=None,
                 suffix='apply_flat_map',
                 timeout=600,
                 **kwargs
                 ):
        """
        Applies a flat map to both DM's, and the IrisAO if it is installed, for a long time (default
        timeout = 10 minutes), or stop it sooner with the stop button.
        :param dm1_command_object: (DmCommand) DmCommand object to apply on DM1.
        :param dm1_command_object: (DmCommand) DmCommand object to apply on DM2.
        :param iris_ao_command_object: (SegmentedDmCommand) SegmentedDmCommand to apply on IrisAO
        :param timeout:  int. Maximum time in seconds to hold the pattern on the DMs. Default 600 sec = 10 min.

        """
        super().__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.timeout = timeout
        self.dm1_command_object = dm1_command_object
        self.dm2_command_object = dm2_command_object
        self.iris_ao_command_object = iris_ao_command_object

    def experiment(self):
        with testbed.dm_controller() as dm, \
             testbed.iris_ao() as iris_ao:

            dm.apply_shape_to_both(self.dm1_command_object, self.dm2_command_object)
            iris_ao.apply_shape(self.iris_ao_command_object)

            self.log.info("Flat Maps applied to both Bostons, and IrisAO if it is installed.")
            self.log.info(f" ** This will loop for up to {self.timeout} seconds , maintaining the flat map. **")
            self.log.info(" ** You must cancel the script to terminate it sooner . ** ")
            self.log.info(" ** I.e. use square 'stop' button in PyCharm. Caution - be careful to single click, not double click it! ** ")

            for time_counter in range(self.timeout):
                time.sleep(1)

            self.log.info(f"Reached DM pattern hold timeout ({self.timeout} seconds);  therefore ending script.")
