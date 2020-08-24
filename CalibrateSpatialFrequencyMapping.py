# flake8: noqa: E402
import os
import hicat.simulators
sim = hicat.simulators.auto_enable_sim()

import numpy as np
from skimage.feature import register_translation  # WARNING! Deprecated in skimage v0.17
from scipy.linalg import polar
from astropy.io import fits
from catkit.catkit_types import quantity, units, SinSpecification, FpmPosition, LyotStopPosition, \
    ImageCentering  # noqa: E402
from catkit.hardware.boston.commands import flat_command
from catkit.hardware.boston.sin_command import sin_command  # noqa: E402

from hicat import util
from hicat.config import CONFIG_INI
from hicat.experiments.Experiment import Experiment  # noqa: E402
from hicat.hardware import testbed  # noqa: E402
from hicat.hardware.testbed import move_filter
from hicat.wfc_algorithms import stroke_min
from astropy.io import ascii


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


def postprocess_images(images, reference_image, speckles,
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
    pipeline_images = np.zeros((len(speckles), 4, *shape))

    for n, (fx, fy) in enumerate(speckles):
        image = images[..., n]

        # Postprocess image to extract speckle centroids
        difference = image - reference_image

        # Split the image into halves, each containing one of the two injected speckles
        pos = difference * (fx * xg + fy * yg > 0)
        neg = difference * (fx * xg + fy * yg < 0)

        # Cross-correlate the two halves to find the separation distance and direction.  This is
        # independent of the global centering of the image, so it is more robust to image jitter
        # on hardware experiments.
        shifts, _, _ = register_translation(pos, neg, upsample_factor=1)
        pipeline_images[n, ...] = np.moveaxis(
            np.dstack([
                image,
                difference,
                pos,
                neg
            ]), 2, 0)

        # Reverse order to get (col, row) ordering, which is the same as (x, y).
        # Separation from origin is half the measured baseline between the two speckles
        centroid = np.array(shifts[::-1]) / 2

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

    def __init__(self, inner_radius, outer_radius, num_speckle, amplitude=None,
                 file_mode=True,
                 auto_expose=True,
                 num_exposures=40,
                 exposure_time=140000,  # microseconds
                 raw_skip=0
                ):
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

        :param inner_radius: float, the inner radius of the sample region in cycles/DM.
        :param outer_radius: float, the outer radius of the sample region in cycles/DM.
        :param num_speckle: int, number of speckles to inject.  Must be >= 3.  The injected
                            speckles are chosen randomly from a uniform distribution over the
                            focal-plane annulus between inner_radius and outer_radius.
        :param amplitude: float, amplitude of injected speckles in nanometers. If None, defaults
                          to the value dm1_ideal_poke or dm2_ideal_poke in the boston_kilo952
                          section of the config file.
        """
        super().__init__()
        self.inner_radius = inner_radius
        self.outer_radius = outer_radius
        self.num_speckle = num_speckle
        self.amplitude = amplitude

        # Parameters for imaging
        self.file_mode = file_mode
        self.auto_expose = auto_expose
        self.num_exposures = num_exposures
        self.exposure_time = exposure_time
        self.raw_skip = raw_skip


        # Additional setup items
        self.suffix = 'dm_spatial_frequency_calibration'
        self.output_path = util.create_data_path(suffix=self.suffix)
        # These don't affect the imaging wavelength at all; they are just passed into the
        # take_exposure_hicat() function from stroke_min.py, which uses it to generate
        # directory names
        if CONFIG_INI['testbed']['laser_source'] == 'light_source_assembly':
            self.wavelength = 640  # center wavelength of LSA source, nm
        else:
            self.wavelength = 638  # center wavelength of MCLS1 source, nm

    def take_exposure(self,
                      devices,
                      initial_path,
                      suffix='',
                      dm1_actuators=None,
                      dm2_actuators=None):
        """
        Take an exposure on HiCAT.

        :param devices: handles to HiCAT hardware
        :param initial_path: root path on disk where raw data is saved
        :param suffix: string, appends this to the end of the timestamp, passed to take_exposure_hicat()
        :param dm1_actuators: array, DM1 actuator vector, in nm, passed to take_exposure_hicat()
        :param dm2_actuators: array, DM2 actuator vector, in nm, passed to take_exposure_hicat()
        :return: numpy array and header
        """

        image, header = stroke_min.take_exposure_hicat(
            dm1_actuators,
            dm2_actuators,
            devices,
            wavelength=self.wavelength,
            exposure_type='coron',
            exposure_time=self.exposure_time,
            auto_expose=self.auto_expose,
            initial_path=initial_path,
            num_exposures=1 if sim else self.num_exposures,
            suffix=suffix,
            file_mode=self.file_mode,
            raw_skip=self.raw_skip)

        return image, header

    def experiment(self):
        self.log.info(f"""Running DM spatial frequency calibration with following parameters:
   inner radius: {self.inner_radius} cycles
   outer radius: {self.outer_radius} cycles
    num_speckle: {self.num_speckle}
      amplitude: {self.amplitude} nm
        """)
        # Select azimuthal angle from uniform distribution over [0, 2pi]
        thetas = np.pi * np.random.rand(self.num_speckle)

        # Select radii using inverse transform sampling so that speckles are uniformly distributed
        # over the annulus between inner_radius and outer_radius
        # See https://math.stackexchange.com/questions/2530527/
        radii = np.sqrt(np.random.rand(self.num_speckle) * (self.outer_radius ** 2 - self.inner_radius ** 2)
                        + self.inner_radius ** 2)

        # Generate (fx, fy) spatial frequency pairs
        speckles = [(R * np.cos(theta), R * np.sin(theta)) for R, theta in zip(radii, thetas)]

        with testbed.laser_source() as laser, \
                testbed.dm_controller() as dm, \
                testbed.motor_controller() as motor_controller, \
                testbed.apodizer_picomotor_mount() as apodizer_picomotor_mount, \
                testbed.quadcell_picomotor_mount() as quadcell_picomotor_mount, \
                testbed.beam_dump() as beam_dump, \
                testbed.imaging_camera() as cam, \
                testbed.pupil_camera() as pupilcam, \
                testbed.temp_sensor(config_id="aux_temperature_sensor") as temp_sensor, \
                testbed.target_acquisition_camera() as ta_cam, \
                testbed.color_wheel() as color_wheel, \
                testbed.nd_wheel() as nd_wheel:

            devices = {'laser': laser,
                       'dm': dm,
                       'motor_controller': motor_controller,
                       'beam_dump': beam_dump,
                       'imaging_camera': cam,
                       'pupil_camera': pupilcam,
                       'temp_sensor': temp_sensor,
                       'color_wheel': color_wheel,
                       'nd_wheel': nd_wheel}

            num_actuators = stroke_min.dm_mask.sum()
            flat = np.zeros(num_actuators)  # Flat DM command

            # Reference image with no injected speckles
            reference_image, _ = self.take_exposure(
                devices,
                initial_path=os.path.join(self.output_path, 'reference'),
                dm1_actuators=flat,
                dm2_actuators=flat)
            reference_image = reference_image.shaped
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

                for n, (R, theta) in enumerate(zip(radii, thetas)):
                    total_image = 0.
                    # Note: in a previous version of this script, I injected both a positive and
                    # a negative speckle and then averaged the two images.  This helps to reject
                    # some of the coherent interference between the injected speckle and the
                    # background speckles, and improves the accuracy of the eventual centroid
                    # estimate.  However, this requires that the two images are globally
                    # registered to each other which is hard to guarantee on hardware; if they
                    # aren't, we lose even more accuracy than we gain by averaging.  Therefore,
                    # I have removed this for now, but could return to it in the future.
                    for sign in [1]:
                        self.log.info(f"Applying sine wave on DM{dm_num} at angle {theta} with "
                                      f"{R} cycles/DM.")
                        sine = sign * amplitude * np.sin(2 * np.pi * R * (
                                np.cos(theta) * stroke_min.actuator_grid.x +
                                np.sin(theta) * stroke_min.actuator_grid.y))[stroke_min.dm_mask]

                        initial_path = os.path.join(self.output_path,
                                                    f"dm{dm_num}_cycle_{R:0.3f}_ang_{theta:0.3f}")
                        image, _ = self.take_exposure(devices, initial_path=initial_path,
                                                      dm1_actuators=sine if dm_num == 1 else flat,
                                                      dm2_actuators=sine if dm_num == 2 else flat)
                        total_image += image.shaped
                    images[..., n] = total_image

                centroids, pipeline_images = postprocess_images(images,
                                                                reference_image,
                                                                speckles,
                                                                reflect_x,
                                                                reflect_y,
                                                                self.log)

                results_table = {
                    'R [cycles/DM]': radii,
                    'theta [rad]': thetas,
                    'fx [cycles/DM]': radii * np.cos(thetas),
                    'fy [cycles/DM]': radii * np.sin(thetas),
                    'cx [pix]': centroids[0, :],
                    'cy [pix]': centroids[1, :]
                }

                ascii.write(results_table, os.path.join(self.output_path, f'results_table_dm'
                                                                          f'{dm_num}.csv'),
                            format='csv')
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