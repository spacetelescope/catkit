import copy
import time

import hicat.simulators

from catkit.hardware.boston.commands import flat_command

import hicat.util
from hicat.control.target_acq import MotorMount, TargetCamera, TargetAcquisition
from hicat.hardware import testbed
from hicat.experiments.Experiment import Experiment
from hicat.hardware.testbed import move_filter


class TargetAcquisitionExperiment(Experiment):

    name = "Independent Target_Acquisition Experiment"

    def __init__(self, *args, extensions=[], num_iterations=1, **kwargs):
        # Initialize output path and logging
        self.extensions = extensions
        self.num_iterations = num_iterations
        super().__init__()
        self.log.info(f"LOGGING: {self.output_path}  {self.suffix}")
        self.args = args
        self.kwargs = kwargs

    def experiment(self):
        with testbed.laser_source() as laser, \
                testbed.dm_controller() as dm, \
                testbed.motor_controller() as motor_controller, \
                testbed.apodizer_picomotor_mount() as apodizer_picomotor_mount, \
                testbed.quadcell_picomotor_mount() as quadcell_picomotor_mount, \
                testbed.beam_dump() as beam_dump, \
                testbed.imaging_camera() as sci_cam, \
                testbed.target_acquisition_camera() as ta_cam, \
                testbed.color_wheel() as color_wheel, \
                testbed.nd_wheel() as nd_wheel:

            self.devices = {'laser': laser,
                            'dm': dm,
                            'motor_controller': motor_controller,
                            'beam_dump': beam_dump,
                            'imaging_camera': sci_cam,
                            'color_wheel': color_wheel,
                            'nd_wheel': nd_wheel}

            # Instantiate TA Controller and run initial centering
            self.ta_devices = {'picomotors': {MotorMount.APODIZER: apodizer_picomotor_mount,
                                              MotorMount.QUAD_CELL: quadcell_picomotor_mount},
                               'beam_dump': beam_dump,
                               "cameras": {TargetCamera.SCI: sci_cam,
                                           TargetCamera.TA: ta_cam}}

            with TargetAcquisition(self.ta_devices,
                                   self.output_path,
                                   *self.args,
                                   **self.kwargs
                                   ) as self.ta_controller:

                # Flatten DMs before attempting initial target acquisition.
                ta_dm_flat = flat_command(bias=False, flat_map=True)
                self.devices["dm"].apply_shape_to_both(ta_dm_flat, copy.deepcopy(ta_dm_flat))

                # Now setup filter wheels.
                move_filter(wavelength=640,
                            nd="clear_1",
                            devices={"color_wheel": self.devices["color_wheel"], "nd_wheel": self.devices["nd_wheel"]})

                for i in range(self.num_iterations):
                    start_time = time.time()
                    self.ta_controller.acquire_target()
                    #self.ta_controller.misalign(motor_mount=MotorMount.APODIZER, target_camera=TargetCamera.SCI)
                    self.log.info(f"TA runtime: {(time.time() - start_time)/60:.3}mins")
                    #self.ta_controller.move((1000, 1000), MotorMount.APODIZER, units="steps")

                # self.extensions allows for this experiment to be extended.
                for extension in self.extensions:
                    extension()
