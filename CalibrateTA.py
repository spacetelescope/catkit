import time

import numpy as np
from photutils import centroid_1dg
import skimage.feature
from catkit.catkit_types import FlipMountPosition

from hicat.experiments.TargetAcquisition import TargetAcquisitionExperiment
from hicat.control.target_acq import MotorMount, TargetCamera


class CalibrateTargetAcquisition(TargetAcquisitionExperiment):

    name = "Target Acquisition Calibration"

    def __init__(self, motor_camera_pairs):
        super().__init__()
        self.motor_camera_pairs = motor_camera_pairs
        self.extensions.extend([self.calibrate_motors, self.find_hole])#, self.calibrate_fpm_center])

    def calibrate_motors(self, n_samples=5):
        t0 = time.time()

        pixels_per_step = {key: [] for key in self.motor_camera_pairs}
        runtimes = {key: [] for key in self.motor_camera_pairs}

        for motor_mount, target_camera in self.motor_camera_pairs:
            for i in range(n_samples):
                self.log.info(f"Calibrating {motor_mount} relative to {target_camera}. Sample {i+1}/{n_samples}")
                start_time = time.time()
                calibration_values = self.ta_controller.calibrate_motors(motor_mount=motor_mount, target_camera=target_camera)
                pixels_per_step[(motor_mount, target_camera)].append(calibration_values)
                runtimes[(motor_mount, target_camera)].append(time.time() - start_time)

        self.log.info(f"Target acquisition motor calibration complete. All {n_samples} taken. (runtime: ~{(time.time() - t0)/60}mins)")
        for combo in self.motor_camera_pairs:
            mean_calibration_value = np.mean(pixels_per_step[combo], axis=0)
            mean_runtime = np.mean(runtimes[combo], axis=0)/60
            self.log.info(f"Mean calibrated pixels/step values for {combo}: {mean_calibration_value}. (runtime ~{mean_runtime}mins)")

    def calibrate_fpm_center(self, n_samples=20):
        t0 = time.time()

        fpm_pixel_coords = []
        runtimes = []

        target_camera = TargetCamera.TA
        for i in range(n_samples):
            start_time = time.time()
            self.ta_controller.acquire_target()

            background_image = self.ta_controller.capture_n_exposures(target_camera,
                                                                      exposure_time=100,
                                                                      n_exposures=10,
                                                                      exposure_period=1,
                                                                      beam_dump_position=FlipMountPosition.IN_BEAM)

            image = self.ta_controller.capture_n_exposures(target_camera,
                                                           exposure_time=100,
                                                           n_exposures=10,
                                                           exposure_period=1)

            image = image - background_image

            clipped_image = np.where(image > 1, 1, 0)

            fpm_pixel_coords.append(centroid_1dg(clipped_image))
            runtimes.append(time.time() - start_time)

        self.log.info(f"Target center calibrated . All {n_samples} taken. (runtime: ~{(time.time() - t0)/60}mins)")
        mean_calibration_value = np.mean(fpm_pixel_coords, axis=0)
        mean_runtime = np.mean(runtimes, axis=0)/60
        self.log.info(f"Mean target pixel coords for {target_camera}: {mean_calibration_value}. (runtime ~{mean_runtime}mins)")

    def find_hole(self,
                  image_crop={TargetCamera.TA: 10, TargetCamera.SCI: 10},
                  ta_canny_threshold={TargetCamera.TA: 10, TargetCamera.SCI: 40}):
        """ Finds the hole for each camera. Note, due to the complexity of
        certain modes this neccesitates some call and response.

        Returns
        -------
        ta_hole : tupel of floats
            The (x,y) position of the FPM hole center for the TA Camera.
        sci_hole : tupel of floats
            The (x,y) position for the FPM hole center for the Imaging Camera.
        """

        calibrated_fpm_center = {target_camera: None for target_camera in TargetCamera}
        for target_camera in TargetCamera:
            # power_switch("light")

            self.ta_controller.acquire_target()

            if target_camera is TargetCamera.SCI:
                self.ta_controller.misalign()

            img = self.ta_controller.capture_n_exposures(target_camera)

            # Artificially crop image in case of edge effects
            img[:image_crop[target_camera], :image_crop[target_camera]] = 0
            img[-1 * image_crop[target_camera]:, -1 * image_crop[target_camera]:] = 0

            # Find edges with skimage
            edges = skimage.feature.canny(img / (ta_canny_threshold[target_camera] * np.median(img)))
            x_circle, y_circle = np.where(edges)
            calibrated_fpm_center[target_camera] = np.median(x_circle), np.median(y_circle)

        for target_camera in TargetCamera:
            self.log.info(f'FPM hole center found for {target_camera}: {calibrated_fpm_center[target_camera]}.')


if __name__ == "__main__":
    CalibrateTargetAcquisition(motor_camera_pairs=[(MotorMount.APODIZER, TargetCamera.TA),
                                                    (MotorMount.APODIZER, TargetCamera.SCI)]).start()
