import time

import hicat.simulators  # auto enables sim if not on HiCAT PC
import hicat.util
from hicat.control.align_lyot import LyotStopAlignment
from hicat.experiments.Experiment import Experiment
from hicat.hardware import testbed 


class AlignLyotStop(Experiment):
    """ Class to run the Lyot Stop Alignment as an experiment. """

    def __init__(self):
        self.name = "Independent Lyot Stop Alignment Experiment"
        super().__init__()

    def experiment(self):

        # Make sure fpm illuminator / beam dump are squared away 
        testbed.remove_all_flip_mounts()
        
        with testbed.pupil_camera() as pupil_cam:

            start_time = time.time()
            lyot_stop_controller = LyotStopAlignment(pupil_cam=pupil_cam,
                                                     output_path_root=self.output_path,
                                                     calculate_pixel_scale=True)
            lyot_stop_controller.iterative_align_lyot_stop(inject_test_offset=True)

            self.log.info(f"LS Alignment runtime: {(time.time() - start_time)/60:.3}mins")

if __name__ == "__main__":
    AlignLyotStop().start()
