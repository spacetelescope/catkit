# flake8: noqa: E402
import os

import matplotlib.pyplot as plt
import numpy as np
from astropy.io import ascii
from astropy.io import fits
from scipy.linalg import polar, logm
from skimage.feature import register_translation  # WARNING! Deprecated in skimage v0.17

from hicat import util
from hicat.config import CONFIG_INI
from hicat.experiments.Experiment import Experiment  # noqa: E402
from hicat.hardware import testbed  # noqa: E402
from hicat.wfc_algorithms import stroke_min


def compute_centroid(image):
    """
    Compute the centroid location of an image.

    :param image: array_like
    """
    x = np.arange(-image.shape[1] // 2, image.shape[1] // 2)
    y = np.arange(-image.shape[0] // 2, image.shape[0] // 2)
    xg, yg = np.meshgrid(x, y)
    denom = image.sum()
    return np.array([(xg * image).sum() / denom, (yg * image).sum() / denom])


def postprocess_images(images, reference_image, speckles,
                       reflect_x=False, reflect_y=False, log=None, window_radius=20):
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
    xgrid, ygrid = np.meshgrid(col, row)

    if reflect_x:
        xgrid = np.fliplr(xgrid)

    if reflect_y:
        ygrid = np.flipud(ygrid)

    centroids = np.zeros((2, len(speckles)))
    pipeline_images = np.zeros((len(speckles), 5, *shape))

    for n, (fx, fy) in enumerate(speckles):
        image = images[..., n]

        # # Postprocess image to extract speckle centroids
        # difference = image - reference_image
        divider = fx * xgrid + fy * ygrid

        # Split the image into halves, each containing one of the two injected speckles
        pos = image * (divider > 0)
        pos_max_ind = np.unravel_index(np.argmax(pos, axis=None), pos.shape)
        pos_masked = pos * ((xgrid - xgrid[pos_max_ind]) ** 2 +
                            (ygrid - ygrid[pos_max_ind]) ** 2 <
                            (window_radius ** 2))

        neg = image * (divider < 0)
        neg_max_ind = np.unravel_index(np.argmax(neg, axis=None), neg.shape)
        neg_masked = neg * ((xgrid - xgrid[neg_max_ind]) ** 2 +
                            (ygrid - ygrid[neg_max_ind]) ** 2 <
                            (window_radius ** 2))
        pos_centroid = compute_centroid(pos_masked)
        neg_centroid = compute_centroid(neg_masked)
        centroid = (pos_centroid - neg_centroid) / 2

        pipeline_images[n, ...] = np.moveaxis(
            np.dstack([
                image,
                pos,
                pos_masked,
                neg,
                neg_masked
            ]), 2, 0)

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
    X = np.zeros((2, len(speckles)), dtype=np.float64)  # Inputs
    Y = np.zeros_like(X)  # Outputs

    for n, (fx, fy) in enumerate(speckles):
        X[:, n] = np.array([fx, fy])
        Y[:, n] = centroids[:, n]

    return Y @ np.linalg.pinv(X.T).T   # Compute the right-sided pseudoinverse


def extract_parameters(mapping_matrix, off_diagonal_tol=1e-2, theta_tol=10., log=None):
    """
    Estimate the rotation angle and horizontal/vertical scaling components of a linear
    transformation of the form y = Ax, where A is a real-valued 2x2 matrix.

    We can decompose A using the polar decomposition into the form A = RS, where R is unitary (a
    combination of rotations and reflections) and S is orthogonal.  In this application, R will be
    a pure rotation matrix.  The R and S matrices can be written as

                                            R = cos(theta) sin(theta)       (2)
                                               -sin(theta) cos(theta)
                                            S = s_x  s_yx                   (4)
                                                s_xy  s_y

    where s_x and s_y are the scaling factors along the horizontal and vertical directions in
    units of pixels / (cycles/DM), m is the shear coefficient, and s_yx and s_xy are off-diagonal
    terms that represent cross-coupling between the x- and y-axes.  If the mapping consists
    PURELY of rotation, horizontal scaling, and vertical scaling, then s_yx and s_xy will vanish
    and S will be purely diagonal.

    :param mapping_matrix: 2x2 numpy array in the form described by Eq. (1)
    :param theta_tol: float, how large the estimated rotation angle can be (in degrees) before we
                      issue a warning, since the HiCAT DMs are known to be well-aligned and
                      should have a rotation angle close to zero.
    :param log: logger object, for displaying warnings
    :return: (s_x, s_y, theta, s_yx, s_xy) with theta in degrees.  S01 and S10 are the off-diagonal
             elements of the scaling matrix, which should be small.
    """
    R, S = polar(mapping_matrix)
    assert np.isclose(np.linalg.det(R), 1.)
    theta = logm(R)[0, 1] * 180 / np.pi  # Matrix log is more numerically stable than inverse trig

    # Scale along horizontal and vertical directions, in (binned pixels) / (cycles/DM)
    s_x, s_y = S[0, 0], S[1, 1]

    # Cross-coupling terms, which we would like to be zero.
    s_yx, s_xy = S[0, 1], S[1, 0]

    return s_x, s_y, theta, s_yx, s_xy


def jackknife_estimator(inputs, outputs):
    """
    Use statistical jackknifing to estimate parameters of interest, along with their standard
    errors.  Given a set of N input vectors and N output vectors, the parameters of interest are
    estimated N times, in each case leaving out exactly one input/output pair.  The resulting
    parameter estimates are used to construct unbiased estimators for the mean and standard error of
    the parameter estimators.

    :param inputs: 2xN array of input vectors
    :param outputs: 2xN array of measured outputs
    :return: (means, standard errors).  Each is a 5-element array.
    """
    num_samples = inputs.shape[1]
    indices = np.arange(num_samples)

    # Compute the parameters using the full set of samples
    full_sample_matrix = outputs @ np.linalg.pinv(inputs)
    full_sample_estimates = np.array(extract_parameters(full_sample_matrix))

    # Jackknife replicates are parameter estimates obtained by leaving one sample out at a time.
    # Therefore, if there are N total samples, there will be N replicates.
    replicates = np.empty((num_samples, 5), dtype=np.float64)
    for n in range(num_samples):
        matrix = outputs[:, indices != n] @ np.linalg.pinv(inputs[:, indices != n])
        replicates[n, :] = extract_parameters(matrix)

    # Compute the empirical mean of each parameter
    empirical_means = replicates.mean(axis=0)

    # Compute standard error of each estimator
    std_err = np.sqrt(((num_samples - 1) / (num_samples)) * np.sum(
        (replicates - empirical_means) ** 2, axis=0))

    # Compute bias of estimator.  This can be subtracted from the parameter estimates to yield
    # unbiased estimates.
    bias = (num_samples - 1) * (full_sample_estimates - empirical_means)

    return full_sample_estimates - bias, std_err


def bootstrap_estimator(inputs, outputs, num_trials, subset_size=None):
    """
    Use statistical bootstrapping to estimate the probability distribution of each parameter
    estimator.  The measured data is treated as the "population," and is resampled num_trials times
    with replacement, and the parameters are computed for each resampled dataset.  The
    distribution of the resulting parameter estimates can be shown to approximate the true
    distribution under a wide range of conditions.

    :param inputs: 2xN array of input vectors
    :param outputs: 2xN array of measured outputs
    :param num_trials: Number of resampled datasets.  Generally >1000 is suitable.
    :param subset_size: Size of resampled datasets.  If None, will default to the size of the
                        original dataset.  This is useful for estimating the precision of the
                        parameter estimates as a function of the number of datapoints, for example
                        if one wishes to approximate how many are necessary to achieve a desired
                        level of precision.
    :return: Nx5 array of bootstrapped parameter estimates.  Each column corresponds to an
             individual parameter.
    """
    num_samples = inputs.shape[1]

    if subset_size is None:
        subset_size = num_samples

    bootstrap_estimates = np.empty((num_trials, 5), dtype=np.float64)

    for n in range(num_trials):
        indices = np.random.choice(num_samples, replace=True, size=subset_size)
        bootstrap_matrix = outputs[:, indices] @ np.linalg.pinv(inputs[:, indices])
        bootstrap_estimates[n, :] = extract_parameters(bootstrap_matrix)

    return bootstrap_estimates


def plot_goodness_of_fit(mapping_matrix, inputs, outputs):
    """
    Use the estimated mapping matrix to predict the outputs from the inputs and compare with the
    measured output data to assess performance.

    :param mapping_matrix: 2x2 matrix describing linear map from inputs to outputs
    :param inputs: 2xN array consisting of N input vectors
    :param outputs: 2xN array consisting of N measured output vectors
    :return: figure and axis handle so that user can modify figure outside of this function if
    needed
    """
    # Figure size is chosen so that equal data ranges correspond to equal distances along
    # horizontal and vertical directions in plot
    fig, ax = plt.subplots(figsize=(10, 10 * 140./240))
    predicted_outputs = mapping_matrix @ inputs

    # RMS error between predicted and actual centroids
    rmse = np.sqrt(np.mean(np.linalg.norm(predicted_outputs - outputs, axis=0) ** 2))
    print(f'RMS error: {rmse:0.3f} pix')

    ax.scatter(predicted_outputs[0, :], predicted_outputs[1, :], label='predicted')
    ax.scatter(outputs[0, :], outputs[1, :], label='measured')
    ax.grid(True)
    ax.set_xlim([-120, 120])
    ax.set_ylim([-20, 120])
    ax.axhline(0, color='k', linewidth=1.5)
    ax.axvline(0, color='k', linewidth=1.5)
    ax.set_title('Predicted vs. measured centroids')
    ax.legend(loc='best')
    ax.set_xlabel('x [pix]')
    ax.set_ylabel('y [pix]')
    ax.annotate(f'RMSE={rmse:0.3f} pix', xy=(0.05, 0.05), xycoords='axes fraction')

    return fig, ax


class CalibrateSpatialFrequencyMapping(Experiment):
    name = 'Calibrate DM mapping'

    def __init__(self, inner_radius, outer_radius, num_speckle, amplitude=None,
                 file_mode=True,
                 auto_expose=True,
                 num_exposures=40,
                 exposure_time=140000,  # microseconds
                 raw_skip=None
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
        self.raw_skip = raw_skip if raw_skip is not None else num_exposures+1


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

        Note: for this particular experiment, image centering is disabled in the pipeline.  The
        results of this experiment are relatively insensitive to small amounts of image jitter
        (unlike a wavefront control experiment).  However, the bright speckles injected during
        calibration are bright enough to throw off the image registration.  Mis-registered images,
        unlike jitter, can and will negatively affect the calibration results.

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
            num_exposures=self.num_exposures,
            suffix=suffix,
            file_mode=self.file_mode,
            raw_skip=self.raw_skip,
            return_binned_image=False,
            centering=testbed.ImageCentering.off
        )

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
            estimates = np.zeros((2, 5, 2), dtype=np.float64)  # 2 DMs x 5 parameters x (mean, err)

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

                ascii.write(results_table,
                            os.path.join(self.output_path, f'results_table_dm{dm_num}.csv'),
                            format='csv')
                raw_matrix = reconstruct_mapping_matrix(centroids, speckles)
                fits.writeto(os.path.join(self.output_path, f'raw_matrix_dm{dm_num}.fits'),
                             raw_matrix)
                fits.writeto(os.path.join(self.output_path, f'pipeline_images_dm{dm_num}.fits'),
                             pipeline_images)

                # Reorganize data into form suitable for parameter estimation
                inputs = np.vstack([results_table['fx [cycles/DM]'],
                                    results_table['fy [cycles/DM]']])
                outputs = np.vstack([results_table['cx [pix]'],
                                     results_table['cy [pix]']])

                # Obtain parameter estimates and their standard errors via statistical bootstrapping
                bootstraps = bootstrap_estimator(inputs, outputs, int(1e4))
                estimates[dm_num - 1, :, 0] = bootstraps.mean(axis=0)
                estimates[dm_num - 1, :, 1] = bootstraps.std(axis=0)

                # Use the x-scale, y-scale and theta to reconstruct a matrix consisting purely of
                # rotation and scale
                s_x, s_y, theta = estimates[dm_num - 1, :3, 0]
                c, s = np.cos(theta * np.pi / 180), np.sin(theta * np.pi / 180)
                RS_matrix = np.array([[c, s], [-s, c]]) @ np.diag([s_x, s_y])
                fits.writeto(os.path.join(self.output_path, f'RS_matrix_dm{dm_num}.fits'),
                             RS_matrix)

                # Compare the centroids predicted by the rotation-scale mapping to the measured
                # centroids to assess algorithm performance
                plot_goodness_of_fit(RS_matrix, inputs, outputs)
                plt.savefig(os.path.join(self.output_path, f'inputs_outputs_dm{dm_num}.png'))

                labels = {
                    'tag': ['sx', 'sy', 'theta', 'syx', 'sxy'],
                    'name': [r'$s_x$', r'$s_y$', r'$\theta$', r'$s_{yx}$', r'$s_{xy}$'],
                    'unit': [r'$\mathrm{pix/(cyc/DM)}$', r'$\mathrm{pix/(cyc/DM)}$', '${}^{\circ}$',
                             r'$\mathrm{pix/(cyc/DM)}$', r'$\mathrm{pix/(cyc/DM)}$'],
}
                # Show histograms of each parameter estimate for reference (in case distributions
                # are noticably non-Gaussian)
                for col in range(bootstraps.shape[1]):
                    plt.figure(figsize=(10, 10*2/3))

                    # Good rule of thumb for number of bins is sqrt(number of datapoints)
                    plt.hist(bootstraps[:, col],
                             bins=int(np.floor(np.sqrt(bootstraps.shape[0]))),
                             weights=np.ones(bootstraps.shape[0]) / bootstraps.shape[0],
                             histtype='stepfilled')
                    plt.grid(True)
                    plt.title(f'Distribution of {labels["name"][col]}')
                    plt.xlabel(f'{labels["name"][col]} [{labels["unit"][col]}]')
                    plt.ylabel(f'Probability')
                    plt.savefig(os.path.join(self.output_path,
                                             f'histogram_{labels["tag"][col]}_dm{dm_num}.png'))

        # Print results
        for dm_num in [1, 2]:
            index = dm_num - 1
            s_x, s_y, theta, s_yx, s_xy = estimates[index, :, 0]
            self.log.info(f"""Estimated mapping parameters for DM {dm_num} (+- 3 std. dev.):
                x scale: {s_x:0.5f} +- {3 * estimates[index, 0, 1]:0.5f} pixels/(cycles/DM)
                y scale: {s_y:0.5f} +- {3 * estimates[index, 1, 1]:0.5f} pixels/(cycles/DM)
                  theta: {theta:0.5f} +- {3 * estimates[index, 2, 1]:0.5f} degrees
                   s_yx: {s_yx:0.5f} +- {3 * estimates[index, 3, 1]:0.5f} pixels/(cycles/DM)
                   s_xy: {s_xy:0.5f} +- {3 * estimates[index, 4, 1]:0.5f} pixels/(cycles/DM)
            """)
