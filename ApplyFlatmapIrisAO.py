import logging
import time

from hicat.experiments.Experiment import Experiment
from hicat.experiments.modules import iris_ao
from hicat.hardware import testbed


class ApplyFlatmapIrisAO(Experiment):
    name = "Apply Flatmap IrisAO"
    log = logging.getLogger(__name__)

    def __init__(self,
                 iris_ao_command_object=None,  # Default custom flat map.
                 output_path=None,
                 suffix='apply_flatmap_irisao',
                 timeout=600,
                 **kwargs
                 ):
        """
        Applies a flat *only* to the IrisAO, if it is installed, for a long time (default
        timeout = 10 minutes), or stop it sooner with the stop button.
        :param iris_ao_command_object: (SegmentedDmCommand) SegmentedDmCommand to apply on IrisAO
        :param timeout:  int. Maximum time in seconds to hold the pattern on the DMs. Default 600 sec = 10 min.

        """
        super().__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.timeout = timeout
        if not iris_ao_command_object:
            self.iris_ao_command_object = iris_ao.flat_command()

    def experiment(self):
        with testbed.iris_ao() as iris_ao:

            iris_ao.apply_shape(self.iris_ao_command_object)

            self.log.info("Flatmap applied to the IrisAO if it is installed.")
            self.log.info(f" ** This will loop for up to {self.timeout} seconds , maintaining the flat map. **")
            self.log.info(" ** You must cancel the script to terminate it sooner . ** ")
            self.log.info(" ** I.e. use square 'stop' button in PyCharm. Caution - be careful to single click, not double click it! ** ")

            for time_counter in range(self.timeout):
                time.sleep(1)

            self.log.info(f"Reached IrisAO pattern hold timeout ({self.timeout} seconds);  therefore ending script.")
