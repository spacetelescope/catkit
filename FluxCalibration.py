import numpy as np

from hicat.experiments.Experiment import Experiment
import hicat.hardware.testbed as testbed
from hicat.wfc_algorithms import stroke_min


class FluxCalibration(Experiment):
    name = 'Flux Calibration'

    def __init__(self, num_exp=20,
                 wavelengths=(620, 640, 660)):
        """Flux Calibration Experiment

        This runs the flux calibration / flux attenuation measurement, and nothing else.

        :param num_exp:
        :param wavelengths:
        """
        super().__init__()
        wavelengths = (640,)

        self.file_mode = True
        self.num_exposures = num_exp
        self.raw_skip = num_exp + 1

        self.wavelengths = wavelengths

        # for now, we simply use the same ND 9% for all direct images.
        self.nd_direct = {wavelength: '9_percent' for wavelength in wavelengths}
        self.nd_coron = {wavelength: 'clear_1' for wavelength in wavelengths}

        # Flat DMs suffice for this
        self.dm1_actuators = np.zeros(stroke_min.num_actuators)
        self.dm2_actuators = np.zeros(stroke_min.num_actuators)



    def experiment(self):

        with testbed.laser_source() as laser, \
                testbed.dm_controller() as dm, \
                testbed.motor_controller() as motor_controller, \
                testbed.beam_dump() as beam_dump, \
                testbed.imaging_camera() as cam, \
                testbed.color_wheel() as color_wheel, \
                testbed.nd_wheel() as nd_wheel:
            devices = {'laser': laser,
                       'dm': dm,
                       'motor_controller': motor_controller,
                       'beam_dump': beam_dump,
                       'imaging_camera': cam,
                       'color_wheel': color_wheel,
                       'nd_wheel': nd_wheel}


            self.log.info(f"Measuring flux calibration for wavelengths: {self.wavelengths}")
            # Calculate flux attenuation factor between direct+ND and coronagraphic images
            flux_norm_dir = stroke_min.capture_flux_attenuation_data(wavelengths=self.wavelengths,
                                                                     out_path=self.output_path,
                                                                     nd_direct=self.nd_direct,
                                                                     nd_coron=self.nd_coron,
                                                                     devices=devices,
                                                                     dm1_act=self.dm1_actuators,
                                                                     dm2_act=self.dm2_actuators,
                                                                     num_exp=self.num_exposures,
                                                                     file_mode=self.file_mode,
                                                                     raw_skip=self.raw_skip)

            self.log.info(f"Flux calibration measurement complete.")


if __name__ == '__main__':
    FluxCalibration().start()