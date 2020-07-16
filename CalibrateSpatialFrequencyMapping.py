# flake8: noqa: E402
import os
import matplotlib

matplotlib.use('QT5Agg')
import matplotlib.pyplot as plt
from matplotlib import colors
import scipy.signal
import numpy as np
from astropy.io import fits
from catkit.catkit_types import quantity, units, SinSpecification, FpmPosition, LyotStopPosition, \
    ImageCentering  # noqa: E402
from catkit.hardware.boston.commands import flat_command
from catkit.hardware.boston.sin_command import sin_command  # noqa: E402

import hicat.util  # noqa: E402
from hicat.config import CONFIG_INI
from hicat.experiments.Experiment import Experiment  # noqa: E402
from hicat.hardware import testbed  # noqa: E402


def compute_centroid(image):
    """
    Compute the centroid location of an image.

    :param image: array_like
    """
    x = np.arange(-image.shape[1] // 2, image.shape[1] // 2)
    y = np.arange(-image.shape[0] // 2, image.shape[0] // 2)
    xg, yg = np.meshgrid(x, y)
    denom = image.sum()
    return (xg * image).sum() / denom, (yg * image).sum() / denom,


def postprocess_images(images, reference_image, direct_image,
                       speckles, exclusion_radius, threshold, log=None):
    """
    Postprocess images to find the centroid of one of the two injected speckles.

    :param images: array_like, 3D array with images stacked along 3rd dimension. One per injected speckle pair.
    :param speckles: list of (fx, fy) pairs in cycles/DM
    :param exclusion_radius: int, radius of central region in image that is masked out.  This
                             helps to suppress differential photon noise from the bright image
                             center.
    :param threshold: float, cutoff value for pixels in postprocessed images, relative to
                      maximum absolute value
    :param log: handle to logger objects to print centroid locations to
    :return: list of (col, row) centroid locations (so that they map to (x, y)), and the
             intermediate images from this pipeline as a 4D array
             (speckle, pipeline_stage, row, col).  Saving this array as a FITS file makes the
             pipeline data very convenient to visualize with DS9 because it creates interactive
             slider bars to explore the (speckle, pipeline_stage) values.
    """
    shape = reference_image.shape

    # Pixel coordinate axes
    row = np.arange(-shape[0] // 2, shape[0] // 2)
    col = np.arange(-shape[1] // 2, shape[1] // 2)
    xg, yg = np.meshgrid(col, row)

    centroids = np.zeros((2, len(speckles)))
    pipeline_images = np.zeros((len(speckles), 5, *shape))

    for n, (fx, fy) in enumerate(speckles):
        image = images[..., n]
        # Postprocess image to extract speckle centroids
        difference = image - reference_image
        no_center = difference * (xg ** 2 + yg ** 2 > exclusion_radius ** 2)
        half = no_center * (fx * xg + fy * yg > 0)
        xcorr = scipy.signal.correlate2d(half, direct_image, mode='same')
        pipeline_images[n, ...] = np.moveaxis(
            np.dstack([
                image,
                difference,
                no_center,
                half,
                xcorr
            ]), 2, 0)

        centroid = np.unravel_index(np.argmax(xcorr), xcorr.shape)
        centroids[:, n] = np.array([xg[centroid], yg[centroid]])
        if log is not None:
            log.info(f'Centroid with (fx, fy) = ({fx:0.2f}, {fy:0.2f}): '
                     f'({xg[centroid[0]]:0.2f}, {yg[centroid[1]]:0.2f})')

    return centroids, pipeline_images


def reconstruct_mapping_matrix(centroids, speckles):
    """
    Reconstruct the input-output relationship between 2D spatial frequencies in cycles/DM and
    pixel locations on the detector.  See docstring of CalibrateSpatialFrequencyMapping for more
    details.

    :param centroids: list of (col, row) centroid locations
    :param speckles: list of (fx, fy) spatial frequencies
    :return: 3x3 numpy array with transformation parameters
    """
    X = np.zeros((3, len(speckles)), dtype=np.float64)  # Inputs
    Y = np.zeros_like(X)  # Outputs
    X[2, :] = 1
    Y[2, :] = 1

    for n, (fx, fy) in enumerate(speckles):
        X[:-1, n] = np.array([fx, fy])
        Y[:-1, n] = centroids[:, n]

    return Y @ np.linalg.pinv(X.T).T   # Compute the right-sided pseudoinverse


class CalibrateSpatialFrequencyMapping(Experiment):
    name = 'Calibrate DM mapping'

    def __init__(self, cycles, num_speckle, exclusion_radius, threshold, amplitude=None):
        """
        Measure the matrix that maps spatial frequencies on each DM to pixel locations at the
        detector.  An affine transformation of the form y = Ax + b can be written in terms of an
        augmented linear system

            row     A00 A01 b0     fx
            col  =  A10 A11 b1  *  fy
             1       1   1   0     1

        For each input value of x, we measure the centroid of one of the two speckles that are
        produced in the focal plane.  They are separated by a line in the detector plane with the
        expression

                             fx * m + fy * n = 0

        where [m, n] are the (row, column) coordinates for the detector-plane pixels, with
        [0, 0] at the center of the image.  By convention, we measure the centroid of the speckle
        for which fx * m + fy * n > 0.  Since centroiding each speckle gives us two measurements
        (one row and one column), and we have six unknowns (A00, A01, A10, A11, b0, b1),
        we need to inject three speckle pairs at minimum to characterize the full transformation.

        This measurement is performed for both DMs.

        :param cycles: float, spatial frequency of injected speckles in cycles/DM.  Cannot exceed
                       Nyquist limit, which is 17 cycles/DM.
        :param num_speckle: int, number of speckles to inject.  Must be >= 3.  The injected
                            speckles are equally spaced in rotation angle over the range [0, pi].
        :param exclusion_radius: int, radius of central region in image that is masked out.  This
                                 helps to suppress differential photon noise from the bright image
                                 center.
        :param threshold: float, cutoff value for pixels in postprocessed images, relative to
                          maximum absolute value
        :param amplitude: float, amplitude of injected speckles in nanometers. If None, defaults
                          to the value dm1_ideal_poke or dm2_ideal_poke in the boston_kilo952
                          section of the config file.
        """
        super().__init__()
        self.cycles = cycles
        self.num_speckle = num_speckle
        self.exclusion_radius = exclusion_radius
        self.threshold = threshold
        self.amplitude = amplitude

    def take_image(self, label, fpm_position):
        saveto_path = hicat.util.create_data_path(initial_path=self.output_path,
                                                  suffix=label)
        return testbed.run_hicat_imaging(exposure_time=quantity(50, units.millisecond),
                                         num_exposures=1,
                                         fpm_position=fpm_position,
                                         lyot_stop_position=LyotStopPosition.in_beam,
                                         file_mode=True,
                                         raw_skip=False,
                                         path=saveto_path,
                                         auto_exposure_time=False,
                                         exposure_set_name='coron',
                                         # TODO: this is not always the right centering
                                         centering=ImageCentering.custom_apodizer_spots,
                                         auto_exposure_mask_size=5.5,
                                         resume=False,
                                         pipeline=True)

    def experiment(self):
        self.log.info(f"""Running DM spatial frequency calibration with following parameters:
         cycles: {self.cycles}
    num_speckle: {self.num_speckle}
      amplitude: {self.amplitude} nm
        """)
        with testbed.dm_controller() as dm:
            # Take baseline image with DMs flat
            dm.apply_shape_to_both(
                flat_command(bias=False, flat_map=True),
                flat_command(bias=False, flat_map=True))

            thetas = np.arange(0, np.pi, np.pi / self.num_speckle)  # Rotation angles of speckles
            speckles = [(self.cycles * np.cos(theta), self.cycles * np.sin(theta))
                        for theta in thetas]  # Input (fx, fy) spatial frequency pairs

            # take_image returns a list of images, and a header.  We want the only image in that
            # list.
            reference_image = self.take_image('reference_image', FpmPosition.coron)[0][0]
            direct_image = self.take_image('direct_image', FpmPosition.direct)[0][0]

            plt.figure()
            plt.imshow(direct_image, norm=colors.LogNorm())
            plt.show()

            # Apply sines to one DM at a time
            for dm_num in [1, 2]:
                images = np.zeros((*reference_image.shape, len(speckles)))

                if self.amplitude is not None:
                    amplitude = self.amplitude
                else:
                    amplitude = CONFIG_INI.getfloat('boston_kilo952', f'dm{dm_num}_ideal_poke')

                # When we put a sine wave on one of the DMs, flatten the other one
                dm_flat = 2 if dm_num == 1 else 1

                for n, theta in enumerate(thetas):
                    image = 0.
                    for sign in [-1, 1]:
                        self.log.info(f"Taking sine wave on DM{dm_num} at angle {theta} with {self.cycles} cycles/DM.")
                        sin_specification = SinSpecification(
                            theta * 180 / np.pi,
                            self.cycles, quantity(sign * amplitude, units.nanometer), 0)
                        sin_command_object = sin_command(sin_specification, flat_map=True, dm_num=dm_num)
                        flat_command_object = flat_command(bias=False, flat_map=True, dm_num=dm_flat)

                        dm.apply_shape(sin_command_object, dm_num=dm_num)
                        dm.apply_shape(flat_command_object, dm_num=dm_flat)

                        label = f"dm{dm_num}_cycle_{self.cycles}_ang_{theta}"
                        image += self.take_image(label, FpmPosition.coron)[0][0] / 2

                    images[..., n] = image

                centroids, pipeline_images = postprocess_images(images,
                                                                reference_image,
                                                                direct_image,
                                                                speckles,
                                                                self.exclusion_radius,
                                                                self.threshold,
                                                                self.log)
                mapping_matrix = reconstruct_mapping_matrix(centroids, speckles)
                fits.writeto(os.path.join(self.output_path, f'mapping_matrix_dm{dm_num}.fits'),
                             mapping_matrix)
                fits.writeto(os.path.join(self.output_path, f'pipeline_images_dm{dm_num}.fits'),
                             pipeline_images)
