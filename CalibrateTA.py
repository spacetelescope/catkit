import os
import time

import numpy as np
from photutils import centroid_1dg, centroid_2dg
from catkit.catkit_types import FlipMountPosition
import matplotlib.pyplot as plt

from hicat.plotting.plot_utils import careful_savefig
from hicat.experiments.TargetAcquisition import TargetAcquisitionExperiment
from hicat.control.target_acq import Alignment, MotorMount, TargetCamera
import hicat.hardware.testbed as testbed

class CalibrateTargetAcquisition(TargetAcquisitionExperiment):

    name = "Target Acquisition Calibration"

    def __init__(self, motor_camera_pairs):
        super().__init__()
        self.motor_camera_pairs = motor_camera_pairs
        self.extensions.extend([self.calibrate_motors])#self.calibrate_alignment_thresholds])#self.calibrate_motors, self.find_hole])#, self.calibrate_fpm_center])

    def compare_centroiding_methods(self, motor_mount=MotorMount.APODIZER, target_camera=TargetCamera.SCI):
        start_time = time.time()

        # Start with PSF on target.
        self.ta_controller.acquire_target()

        # Force the use of only default centroid methods.
        cached_non_default_centroid_method = self.ta_controller.centroid_methods[target_camera]["non_default"]
        try:
            self.ta_controller.centroid_methods[target_camera]["non_default"] = self.ta_controller.centroid_methods[target_camera]["default"]

            # Missalign such that PSF is away from the FPM.
            self.ta_controller.misalign(motor_mount, target_camera)

            n_moves = 20
            _centered, *delta_from_center = self.ta_controller.is_centered(target_camera, check_threshold=False)
            move_pixel_step = [(delta / n_moves) for delta in delta_from_center]
            self.log.info(
                f"PSF missaligned by {self.ta_controller.misalignment_step_size}. Incrementally moving back towards center by {move_pixel_step} pixels over a total of {n_moves} moves.")

            target_pixel = self.ta_controller.get_target_pixel(target_camera)
            centroid_deltas = {"1d": [], "2d": []}
            for i in range(n_moves):
                # Move.
                self.ta_controller.move(move_pixel_step,
                                        motor_mount=motor_mount,
                                        target_camera=target_camera)

                image = self.ta_controller.capture_n_exposures(target_camera,
                                                               exposure_time=self.ta_controller.exposure_time[target_camera])

                x, y = centroid_1dg(image)
                centroid_deltas["1d"].append((x - target_pixel[0], y - target_pixel[1]))
                x, y = centroid_2dg(image)
                centroid_deltas["2d"].append((x - target_pixel[0], y - target_pixel[1]))
        finally:
            self.ta_controller.centroid_methods[target_camera]["non_default"] = cached_non_default_centroid_method

        self.log.info(f"Centroid testing complete. ({(time.time() - start_time)/60}min)")

        # Check whether PSF ended up through the FPM hole and onto the TA camera.
        if self.ta_controller._update_alignment_state() is not Alignment.COARSE_ALIGNED:
            self.log.warning(f"Centroid testing failed to make it through the FPM hole and onto the TA camera. Motors need recalibrating.")

        # Plot
        plt.clf()
        fig = plt.figure(figsize=(12, 8))
        ax = fig.add_subplot(1, 1, 1)
        ax.plot([x[0] for x in centroid_deltas["1d"]], [x[1] for x in centroid_deltas["1d"]], "b*-", label="1d")
        ax.plot([x[0] for x in centroid_deltas["2d"]], [x[1] for x in centroid_deltas["2d"]], "r.-", label="2d")
        ax.set_xlabel("x pixel distance from target")
        ax.set_ylabel("y pixel distance from target")
        ax.set_title(f"Centroid comparison for {motor_mount} relative to {target_camera}.")
        ax.legend()
        ax.grid(True)

        # Save
        careful_savefig(fig, os.path.join(self.ta_controller.ta_output_path, "centroid_test.pdf"))
        plt.close(fig)

    def calibrate_alignment_thresholds(self):
        """ Move PSF by small-ish steps and measure total image counts as we do.
            The idea is to observe adequate thresholding ratios as the PSF moves through the FPM.
        """
        # Start with PSF on target.
        self.ta_controller.acquire_target()

        # Missalign such that PSF is away from the FPM.
        self.ta_controller.misalign(MotorMount.APODIZER, TargetCamera.SCI)

        n_moves = 20
        _centered, *delta_from_center = self.ta_controller.is_centered(TargetCamera.SCI, check_threshold=False)
        move_pixel_step = [delta / n_moves for delta in delta_from_center]
        self.log.info(
            f"PSF missaligned by {self.ta_controller.misalignment_step_size}. Incrementally moving back towards center by {move_pixel_step} pixels over a total of {n_moves} moves.")

        for i in range(n_moves):
            # Move.
            self.ta_controller.move(move_pixel_step,
                                    motor_mount=MotorMount.APODIZER,
                                    target_camera=TargetCamera.SCI)
            # Utilize this func to take images, log counts, and centroid deltas to later plot.
            for target_camera in TargetCamera:
                self.ta_controller.distance_to_target(target_camera, check_threshold=False)

        self.log.info("Alignment thresholding calibration complete")

        # Check whether PSF ended up through the FPM hole and onto the TA camera.
        if self.ta_controller.alignment is not Alignment.COARSE_ALIGNED:
            self.log.warning(f"Alignment thresholding failed to make it through the FPM hole and onto the TA camera. Motors need recalibrating.")

        # Plot
        plt.clf()
        fig = plt.figure(figsize=(12, 8))
        ax = fig.add_subplot(1, 1, 1)
        ax.plot(self.ta_controller.counts_log[TargetCamera.SCI]["ratio"][-n_moves:], "r.-", lable="SCI camera")
        ax.plot(self.ta_controller.counts_log[TargetCamera.TA]["ratio"][-n_moves:], "b.-", lable="TA camera")
        ax.set_xlabel("Iteration")
        ax.set_ylabel("sum(image)/sum(background)")
        ax.set_title("Count Thresholding Calibration")

        # Save
        careful_savefig(fig, os.path.join(self.ta_controller.ta_output_path, "alignment_threshold_calibration.pdf"))
        plt.close(fig)

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
            self.log.info(f"Mean calibrated pixels/step values for {combo}: {mean_calibration_value}. (mean runtime ~{mean_runtime}mins)")

    def calibrate_fpm_center(self, target_camera=TargetCamera.TA, clip_threshold=0.1, exposure_time=1000000):
        self.ta_controller.calibrate_target_pixel(target_camera=target_camera, clip_threshold=clip_threshold, exposure_time=exposure_time)


if __name__ == "__main__":
    CalibrateTargetAcquisition(motor_camera_pairs=[(MotorMount.APODIZER, TargetCamera.SCI), (MotorMount.APODIZER, TargetCamera.TA)]).start()
