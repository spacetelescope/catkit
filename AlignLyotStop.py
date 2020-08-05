import time

import hicat.simulators  # auto enables sim if not on HiCAT PC
import hicat.util
from hicat.control.align_lyot import LyotStopAlignment
from hicat.experiments.Experiment import Experiment
from hicat.hardware import testbed 

from catkit.catkit_types import FpmPosition


class AlignLyotStop(Experiment):
    """ Class to run the Lyot Stop Alignment as an experiment. """

    def __init__(self, fpm_in=True):
        self.name = "Independent Lyot Stop Alignment Experiment"
        self.fpm_position = FpmPosition.coron if fpm_in else FpmPosition.direct
        super().__init__()

    def experiment(self):

        # Make sure fpm illuminator / beam dump are squared away and FPM is in/out
        testbed.remove_all_flip_mounts()
        testbed.move_fpm(self.fpm_position)
        
        with testbed.motor_controller() as motor_controller, \
                testbed.pupil_camera() as pupilcam:

            ls_align_devices = {'motor_controller': motor_controller, 
                                'pupil_camera': pupilcam}
 
            start_time = time.time()
            lyot_stop_controller = LyotStopAlignment(ls_align_devices,
                                                     output_path_root=self.output_path,
                                                     calculate_pixel_scale=True)
            lyot_stop_controller.iterative_align_lyot_stop(inject_test_offset=True)

            self.log.info(f"LS Alignment runtime: {(time.time() - start_time)/60:.3}mins")

if __name__ == "__main__":
    AlignLyotStop().start()
