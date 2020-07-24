import time

import hicat.simulators  # auto enables sim if not on HiCAT PC
import hicat.util
from hicat.control.align_lyot import LyotStopAlignment
from hicat.experiments.Experiment import Experiment
from hicat.hardware import testbed 


class AlignLyotStop(Experiment):
    """ Class to run the Lyot Stop Alignment as an experiment. """

    name = "Independent Lyot Stop Alignment Experiment"

    def __init__(self):
        
        # Initialize output path and logging
        self.extensions = []
        suffix = self.name
        output_path = hicat.util.create_data_path(suffix=suffix)
        super().__init__(output_path=output_path, suffix=suffix)
        hicat.util.setup_hicat_logging(self.output_path, self.suffix)
        self.log.info(f"LOGGING: {self.output_path}  {self.suffix}")


    def experiment(self):
        
        # Make sure fpm illuminator / beam dump are squared away 
        testbed.remove_all_flip_mounts()

        with testbed.pupil_camera() as pupil_cam:

            start_time = time.time()
            lyot_stop_controller = LyotStopAlignment(pupil_cam=pupil_cam,
                                                     output_path_root=self.output_path,
                                                     calculate_pixel_scale=True)
            lyot_stop_controller.iterative_align_lyot_stop()
            
            # self.extensions allows for this experiment to be extended.
            for extension in self.extensions:
                extension()

            self.log.info(f"LS Alignment runtime: {(time.time() - start_time)/60:.3}mins")

if __name__ == "__main__":
    AlignLyotStop().start()
