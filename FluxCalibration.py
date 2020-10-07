import numpy as np

from hicat.experiments.Experiment import Experiment
import hicat.hardware.testbed as testbed
from hicat.wfc_algorithms import wfsc_utils


class FluxCalibration(Experiment):
    name = 'Flux Calibration'

    def __init__(self, num_exp=20,
                 wavelengths=(620, 640, 660,),
                 short_exposure_time=2000):
        """Flux Calibration Experiment

        This runs the flux calibration / flux attenuation measurement, to determine:
            1. The attenuation factor (product of ND filter transmission and fiber coupling efficiency) in each
               wavelength of interest.
            2. The total flux of the laser in each wavelength of interest, in an unocculted direct image.

        :param num_exp: number of exposures to use at each wavelength.
        :param wavelengths: iterable of wavelengths in nm for which to perform this measurement.
        :param short_exposure_time: float, exp time in microset to use for the short unsaturated direct exposures
        """
        super().__init__()

        self.file_mode = True
        self.num_exposures = num_exp
        self.raw_skip = num_exp + 1

        self.wavelengths = wavelengths

        # for now, we simply use the same ND 9% for all direct images.
        self.nd_direct = {wavelength: '9_percent' for wavelength in wavelengths}
        self.nd_coron = {wavelength: 'clear_1' for wavelength in wavelengths}

        # Flat DMs suffice for this
        self.dm1_actuators = np.zeros(wfsc_utils.num_actuators)
        self.dm2_actuators = np.zeros(wfsc_utils.num_actuators)

        self.short_exposure_time = short_exposure_time


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
            flux_norm_dir = wfsc_utils.capture_flux_attenuation_data(wavelengths=self.wavelengths,
                                                                     out_path=self.output_path,
                                                                     nd_direct=self.nd_direct,
                                                                     nd_coron=self.nd_coron,
                                                                     devices=devices,
                                                                     dm1_act=self.dm1_actuators,
                                                                     dm2_act=self.dm2_actuators,
                                                                     num_exp=self.num_exposures,
                                                                     file_mode=self.file_mode,
                                                                     raw_skip=self.raw_skip,
                                                                     exp_time_unsaturated=self.short_exposure_time)

            self.log.info(f"Flux calibration measurement complete.")


if __name__ == '__main__':
    FluxCalibration().start()