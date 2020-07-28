# flake8: noqa: E402
import os

import numpy as np
from skimage.feature import register_translation  # WARNING! Deprecated in skimage v0.17
from scipy.linalg import polar
from astropy.io import fits
from catkit.catkit_types import quantity, units, SinSpecification, FpmPosition, LyotStopPosition, \
    ImageCentering  # noqa: E402
from catkit.hardware.boston.commands import flat_command
from catkit.hardware.boston.sin_command import sin_command  # noqa: E402

import hicat.util  # noqa: E402
from hicat.config import CONFIG_INI
from hicat.experiments.Experiment import Experiment  # noqa: E402
from hicat.hardware import testbed  # noqa: E402
from hicat.hardware.testbed import move_filter

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


def postprocess_images(images, reference_image, direct_image, speckles,
                       reflect_x=False, reflect_y=False, log=None):
    """
    Postprocess images to find the centroid of one of the two injected speckles.  This is done as
    follows:

        1. Subtract coronagraphic image without speckle to reduce background level
        2. Mask off half of the image to isolate one injected speckle
        3. Cross-correlate with direct image

    The desired speckle location is then given by the location where the cross-correlation is
    maximized.  This is because applying a sinusoidal phase in the pupil plane acts as a
    diffraction grating that generates copies of the direct image at the grating frequency, so
    cross-correlation with the direct image is equivalent to a matched filtering operation.

    If the data is known in advance to contain a reflection component in either the horizontal or
    vertical directions, this can be flagged.  This will flip the corresponding sign of the line
    that divides the focal plane between the two speckles, which ensures that the desired speckle
    is correctly extracted, and will also flip the sign of the centroid in that direction so that
    the affine transformation matrix contains only a rotation and scale.

    Cross-correlation is slower, but more robust than directly computing the center-of-mass of
    the image, because it is less susceptible to residual background after subtraction.
    Thresholding the image to remove background will bias the estimate of the speckle centroid
    location, because some of the desired speckle energy will also be rejected.  This bias becomes
    worse for higher amounts of aberration.

    :param images: array_like, 3D array with images stacked along 3rd dimension. One per injected speckle pair.
    :param reference_image: array_like, coronagraphic image without injected speckles
    :param direct_image: array_like, direct image without injected speckles.
    :param speckles: list of (fx, fy) pairs in cycles/DM
    :param reflect_x: whether there is a known reflection component in the x direction (across
                      the y axis) that we should account for during postprocessing
    :param reflect_y: whether there is a known reflection component in the y direction (across
                      the x axis) that we should account for during postprocessing
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

    if reflect_x:
        xg = np.fliplr(xg)

    if reflect_y:
        yg = np.flipud(yg)

    centroids = np.zeros((2, len(speckles)))
    pipeline_images = np.zeros((len(speckles), 3, *shape))

    for n, (fx, fy) in enumerate(speckles):
        image = images[..., n]

        # Postprocess image to extract speckle centroids
        difference = image - reference_image
        half = difference * (fx * xg + fy * yg > 0)
        shifts, _, _ = register_translation(half, direct_image, upsample_factor=1)
        pipeline_images[n, ...] = np.moveaxis(
            np.dstack([
                image,
                difference,
                half,
            ]), 2, 0)

        centroid = np.array(shifts[::-1])

        if reflect_x:
            centroid[0] *= -1

        if reflect_y:
            centroid[1] *= -1

        centroids[:, n] = centroid
        if log is not None:
            log.info(f'Centroid with (fx, fy) = ({fx:0.2f}, {fy:0.2f}): '
                     f'({centroid[0]:0.2f}, {centroid[1]:0.2f})')

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


def extract_rotation_and_scale(mapping_matrix, off_diagonal_tol=1e-2, theta_tol=10., log=None):
    """
    Estimate the rotation angle and horizontal/vertical scaling components of an affine
    transformation of the form y = Ax + b using the polar decomposition.

    An affine transformation in two dimensions can be represented by the matrix

                                                A00 A01 b0
                                            C = A10 A11 b1          (1)
                                                 0   0   1
    where
                                            A = A00 A01             (2)
                                                A10 A11
                                            b = b0                  (3)
                                                b1

    We can further decompose A using the polar decomposition into the form A = RS, where R is
    unitary (a combination of rotations and reflections), and S is orthonormal.  Ideally,
    in this application, R will be a pure rotation matrix and S will be diagonal:

                                            R = cos(theta) sin(theta)       (4)
                                               -sin(theta) cos(theta)
                                            S = s_x  0                      (5)
                                                 0  s_y

    where s_x and s_y are the scaling factors along the horizontal and vertical directions in
    units of (binned pixels) / (cycles/DM).

    :param mapping_matrix: 3x3 numpy array in the form described by Eq. (1)
    :param off_diagonal_tol: float, how large the off-diagonal elements of S can be before we
                             issue a warning.
    :param theta_tol: float, how large the estimated rotation angle can be (in degrees) before we
                      issue a warning, since the HiCAT DMs are known to be well-aligned and
                      should have a rotation angle close to zero.
    :param log: logger object, for displaying warnings
    :return: (s_x, s_y, theta) with theta in degrees
    """

    A = mapping_matrix[:2, :2]  # 2x2 submatrix in top-left corner: contains rotation/scaling
    b = mapping_matrix[:2, 2]  # First two elements of last column: contains translation

    R, S = polar(A)

    # Average the angles from each of the four elements of the rotation matrix to estimate
    # rotation angle
    theta = np.mean([np.arccos(R[0, 0]), np.arcsin(R[0, 1]),
                    -np.arcsin(R[1, 0]), np.arccos(R[1, 1])]) * 180 / np.pi

    # Rotation should be small
    if np.abs(theta) > theta_tol and log is not None:
        log.warning(f'Estimated rotation is larger than {theta_tol}. Results may not be accurate.')

    # Scaling matrix should be diagonal
    if ((np.abs(S[0, 1]) > off_diagonal_tol or np.abs(S[1, 0]) > off_diagonal_tol)
            and log is not None):
        log.warning('Scaling matrix has significant off-diagonal components. Results may not be '
                    'accurate.')

    # Scale along horizontal and vertical directions, in (binned pixels) / (cycles/DM)
    s_x, s_y = S[0, 0], S[1, 1]

    return s_x, s_y, theta


class CalibrateSpatialFrequencyMapping(Experiment):
    name = 'Calibrate DM mapping'

    def __init__(self, cycles, num_speckle, amplitude=None):
        """
        Measure the matrix that maps spatial frequencies on each DM to pixel locations at the
        detector.  An affine transformation of the form y = Ax + b can be written in terms of an
        augmented linear system

            col     A00 A01 b0     fx
            row  =  A10 A11 b1  *  fy
             1       0   0   1      1

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
        :param amplitude: float, amplitude of injected speckles in nanometers. If None, defaults
                          to the value dm1_ideal_poke or dm2_ideal_poke in the boston_kilo952
                          section of the config file.
        """
        super().__init__()
        self.cycles = cycles
        self.num_speckle = num_speckle
        self.amplitude = amplitude

    def take_image(self, label, fpm_position):
        saveto_path = hicat.util.create_data_path(initial_path=self.output_path,
                                                  suffix=label)
        if fpm_position == FpmPosition.coron:
            exposure_time = quantity(50, units.millisecond)
            move_filter(wavelength=640, nd='clear_1')
            exposure_set_name = 'coron'
        elif fpm_position == FpmPosition.direct:
            exposure_time = quantity(1, units.millisecond)
            move_filter(wavelength=640, nd='9_percent')
            exposure_set_name = 'direct'

        return testbed.run_hicat_imaging(exposure_time=exposure_time,
                                         num_exposures=40,
                                         fpm_position=fpm_position,
                                         lyot_stop_position=LyotStopPosition.in_beam,
                                         file_mode=True,
                                         raw_skip=False,
                                         path=saveto_path,
                                         auto_expose=True,
                                         exposure_set_name=exposure_set_name,
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
            results = np.zeros((2, 3), dtype=np.float64)  # 2 DMs x 3 parameters

            # Apply sines to one DM at a time
            for dm_num in [1, 2]:
                # Account for the mirror-image effect from DM2
                reflect_x = (dm_num == 2)
                reflect_y = False

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
                                                                reflect_x,
                                                                reflect_y,
                                                                self.log)
                mapping_matrix = reconstruct_mapping_matrix(centroids, speckles)
                fits.writeto(os.path.join(self.output_path, f'mapping_matrix_dm{dm_num}.fits'),
                             mapping_matrix)
                fits.writeto(os.path.join(self.output_path, f'pipeline_images_dm{dm_num}.fits'),
                             pipeline_images)

                results[dm_num - 1, :] = np.array(
                    extract_rotation_and_scale(mapping_matrix, log=self.log))

        for dm_num in [1, 2]:
            index = dm_num - 1
            s_x, s_y, theta = results[index, :]
            self.log.info(f"""Estimated mapping parameters for DM {dm_num}:
                x scale: {s_x:0.3f} pixels/(cycles/DM)
                y scale: {s_y:0.3f} pixels/(cycles/DM)
                  theta: {theta:0.3f} degrees
            """)