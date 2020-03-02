import numpy as np
import os
import sys
import logging
import functools
import glob
import hcipy
import shutil
import subprocess
from astropy.io import fits
import time
import tempfile

import hicat
from hicat.config import CONFIG_INI
from hicat.hardware import testbed, testbed_state
from catkit.catkit_types import ImageCentering, quantity, units
from catkit.hardware.boston import DmCommand

#from hicat import data_pipeline as pipeline
from hicat import data_pipeline_lite as pipeline

import hicat.util

log = logging.getLogger(__name__)

# TODO right now this code makes use of the following global variables.
# We should move away from the use of globals if at all possible, to
# make this more modular.

# Creating a grid for the focal plane
# This is only used to calculate which pixels belong to the dark zone
# and for displaying focal-plane images.
num_pix_fp = 178

sampling = CONFIG_INI.getfloat('data_simulator', 'sampling_with_lyot_stop')
pipeline_binning = 4

q = sampling/pipeline_binning
focal_grid = hcipy.make_pupil_grid(num_pix_fp, num_pix_fp / q)

# Create grid and mask for DM actuators in pupil planes. Used in control
# We can load the boston kilo DM mask which is in the simulators folder
hicat_package_root= os.path.dirname(hicat.__file__)
dm_mask = hcipy.read_fits(os.path.join(hicat_package_root, 'simulators', 'boston_kilodm-952_mask.fits')).astype('bool')
num_actuators = int(np.sum(dm_mask))

actuator_grid = hcipy.make_uniform_grid(dm_mask.shape, 1)
dm_mask = hcipy.Field(dm_mask.ravel(), actuator_grid)


##############################################################################
# Functions for taking exposures on the Simulator
# including for generation of Jacobian and observation matrices

def take_exposure_hicat_simulator(dm1_actuators, dm2_actuators, exposure_type='direct', output_path=".",
                                  use_subprocess=False, fast_method=False, apply_pipeline_binning=True, wavelength=638.0):
    """ Wrapper for simulating an exposure or E field and returning as a hcipy.Field

    Note, this function normalizes out the exposure time prior to returning the E or I field.

    :param dm1_actuators: DM1 actuator vector, in nm
    :param dm2_actuators: DM2 actuator vector, in nm
    :param exposure_type: String; 'direct', 'coron', or 'coronEfield'
    :param output_path: Directory path in which to write output files
    :param use_subprocess: Bool, set to True to run simulator in a subprocess
    :param apply_pipeline_binning: Bool, bin images or not?
    :param wavelength: imaging wavelength, in nm

    :returns: Tuple with (Normalized image in units of counts/microsec or sqrt(counts/microsec) for coronEfield,
              FITS header of that image)

    """

    if fast_method:
        # Directly interact with the simulator in this same Python process.
        # No files written to disk for input or output
        from hicat.simulators import optics_simulator
        optics_simulator.dm1.set_surface(dm1_actuators)
        optics_simulator.dm2.set_surface(dm2_actuators)
        optics_simulator.include_fpm = exposure_type=='coron'

        hdu = optics_simulator.take_exposure()

    else:
        # "Traditional" method of invoking the simulator, back compatible with how the
        # Mathematica one worked. Lots of passing data around with files on disk

        simulator_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../hicat/simulators/hicat_sim.py'))

        output_filename = 'sim_image_{}.fits'.format(exposure_type)

        dm1_surface = dm_actuators_to_surface(dm1_actuators)
        dm2_surface = dm_actuators_to_surface(dm2_actuators)

        fname_dm1 = os.path.join(output_path, 'dm_command', 'dm1_command_2d_noflat.fits')
        fname_dm2 = os.path.join(output_path, 'dm_command', 'dm2_command_2d_noflat.fits')

        if not os.path.exists(os.path.join(output_path, 'dm_command')):
            os.makedirs(os.path.join(output_path, 'dm_command'))
        hcipy.write_fits(dm1_surface, fname_dm1)
        hcipy.write_fits(dm2_surface, fname_dm2)

        cmd = [sys.executable, simulator_file, output_path, output_filename, exposure_type, str(wavelength)]

        if use_subprocess:
            # Run simulator in a separate process
            subprocess.check_call(cmd)
            fname = os.path.join(output_path, 'simulated', output_filename)
            with fits.open(fname) as hdu:
                exp_time = hdu[0].header['EXP_TIME']
                data = hdu[0].data
        else:
            # Run simulator in same process, for easier debugging:
            hdu = hicat.simulators.hicat_sim.script_interface(cmd[1:], apply_pipeline_binning=apply_pipeline_binning)
            exp_time = hdu[0].header['EXP_TIME']
            data = hdu[0].data

    # Convert units to cts/second or sqrt(cts/second):
    if exposure_type=='coronEfield':
        result = hcipy.Field((data[0, ...] + 1j * data[1, ...]).ravel(), focal_grid) / np.sqrt(exp_time)
    else:
        result = hcipy.Field(data.ravel(), focal_grid) / exp_time

    return result, hdu[0].header

take_coron_exposure_simulator = functools.partial(take_exposure_hicat_simulator, exposure_type='coron')
take_direct_exposure_simulator = functools.partial(take_exposure_hicat_simulator, exposure_type='direct')
take_electric_field_simulator = functools.partial(take_exposure_hicat_simulator, exposure_type='coronEfield')


##############################################################################
# Functions for taking exposures on the real hardware

def take_exposure_hicat(dm1_actuators, dm2_actuators, devices,
                        exposure_type='coron',
                        num_exposures=10,
                        exposure_time=None,
                        file_mode=True,
                        raw_skip=0,
                        initial_path=None,
                        suffix=None,
                        take_background_exposures=True,
                        use_background_cache=True,
                        wavelength=638.0):
    """Efficient exposure function using list of device handles already obtained

    Apply the provided shapes to both DMs, then take an exposure.
    Assumes you already have handles to all relevant hardware controllers.

    :param dm1_actuators: DM1 actuator vector, in nm
    :param dm2_actuators: DM2 actuator vector, in nm
    :param exposure_type: string, 'direct' or 'coron'
    :param exposure_time: float, exp time in microsec; set to None to use
           default values set in config.ini for coron or direct modes.
    :param devices : dict, Dictionary of device handles for hardware access
    :param num_exposures: number of exposures to take
    :param file_mode: Write output to disk if true, else just return the image
    :param raw_skip:
    :param initial_path: string, Passed to utils.create_data_path.
    :param suffix: string, Passed to utils.create_data_path.
    :param take_background_exposures:
    :param use_background_cache:
    :param wavelength: imaging wavelength (in nm)

    :returns: tuple with (Image in units of counts/microsec, FITS header metadata)

    Notes:
        - This function doesn't move the FPM or filter wheels.  exposure_type and wavelength are only used to generate output directory

    """
    suffix = f"{exposure_type}_{wavelength}" if suffix is None else suffix
    path = hicat.util.create_data_path(initial_path=initial_path, suffix=suffix)

    # Pick wavelength and ND filters
    filter_combo_name = f'bb_{int(np.rint(wavelength))}_{exposure_type}'

    dm1_command_object = DmCommand.DmCommand(dm_actuators_to_surface(dm1_actuators * 1e-9).shaped, dm_num=1,
                                             flat_map=True, bias=False)
    dm2_command_object = DmCommand.DmCommand(dm_actuators_to_surface(dm2_actuators * 1e-9).shaped, dm_num=2,
                                             flat_map=True, bias=False)
    coronagraph = (exposure_type == 'coron')

    if file_mode:
        filename = exposure_type + '_image'

        exp_path = os.path.join(path, filter_combo_name, exposure_type)
        raw_path = os.path.join(exp_path, "raw")
        img_path = os.path.join(raw_path, "images")
        bg_path = os.path.join(raw_path, "backgrounds")
    else:
        filename = None

    if exposure_time is not None:
        exposure_time = quantity(exposure_time, units.microsecond)

    if coronagraph:
        laser_current = CONFIG_INI.getint('thorlabs_source_mcls1', 'coron_current')
        if exposure_time is None:
            exposure_time = quantity(100000, units.microsecond)
        fpm_position = CONFIG_INI.getfloat('motor_FPM_Y', 'default_coron')

        # Check whether we are in CLC mode or APLC mode
        if CONFIG_INI['testbed']['apodizer'] == 'no_apodizer':
            centering = ImageCentering.satellite_spots
        else:
            centering = ImageCentering.global_cross_correlation
    else:
        centering = ImageCentering.psf
        laser_current = CONFIG_INI.getint('thorlabs_source_mcls1', 'direct_current')
        if exposure_time is None:
            exposure_time = quantity(100, units.microsecond)
        fpm_position = CONFIG_INI.getfloat('motor_FPM_Y', 'direct')

    # Move FPM to required position
    testbed.move_fpm(exposure_type, devices=devices)

    # Set laser current
    devices['laser'].set_current(laser_current)

    # Set dm shapes
    devices['dm'].apply_shape_to_both(dm1_command_object, dm2_command_object)

    # Set FPM position
    devices['motor_controller'].absolute_move('motor_FPM_Y', fpm_position)

    # Move beam dump out of the beam
    devices['beam_dump'].move_to_position2()

    # Take images with imaging_camera
    images, metadata = devices['imaging_camera'].take_exposures(exposure_time, num_exposures,
                                                                file_mode=file_mode,
                                                                raw_skip=raw_skip,
                                                                path=img_path,
                                                                filename=filename,
                                                                return_metadata=True)

    # Take a new background image if necessary
    background_images = []
    bg_metadata = None
    if take_background_exposures:
        if use_background_cache and not file_mode:
            log.warning('Warning: Turning off exposure cache feature because it is only supported by file_mode=True.')
            use_background_cache = False

        if use_background_cache and raw_skip != 0:
            log.warning('Warning: Turning off exposure cache feature because it is only supported by raw_skip=0.')
            use_background_cache = False

        if use_background_cache:
            bg_cache_path = testbed_state.check_background_cache(exposure_time, num_exposures)

            if bg_cache_path is not None:
                # Cache was hit.
                log.info('Using cached background exposures: ' + bg_cache_path)
                background_images = glob.glob(os.path.join(bg_cache_path, '*.fits'))

                os.makedirs(bg_path)
                cache_file_path = os.path.join(bg_path, 'cache_directory.txt')

                with open(cache_file_path, mode='w') as cache_file:
                    cache_file.write(bg_cache_path)

            if not background_images:
                # Move beam dump int the beam
                devices['beam_dump'].move_to_position1()

                # Take background exposures
                bg_filename = 'bkg_' + filename if file_mode else None
                background_images, bg_metadata = devices['imaging_camera'].take_exposures(exposure_time, num_exposures,
                                                                                          file_mode=file_mode,
                                                                                          path=bg_path,
                                                                                          filename=bg_filename,
                                                                                          raw_skip=raw_skip,
                                                                                          return_metadata=True)

                if use_background_cache:
                    testbed_state.add_background_to_cache(exposure_time, num_exposures, bg_path)

    final_output = None
    cal_metadata = None
    if file_mode and raw_skip == 0:
        final_output = pipeline.standard_file_pipeline(exp_path, centering=centering)
    if raw_skip > 0:
        final_output = pipeline.data_pipeline(images, background_images, centering, output_path=exp_path,
                                              filename_root=filename, img_metadata=metadata,
                                              bg_metadata=bg_metadata)
    if not file_mode:
        final_output, cal_metadata = pipeline.data_pipeline(images, background_images, centering,
                                                            img_metadata=metadata,
                                                            bg_metadata=bg_metadata,
                                                            return_metadata=True)

    if file_mode:
        if testbed_state.dm1_command_object:
            testbed_state.dm1_command_object.export_fits(exp_path)
        if testbed_state.dm2_command_object:
            testbed_state.dm2_command_object.export_fits(exp_path)
        hicat.util.save_ini(os.path.join(exp_path, 'config'))

    if not file_mode:
        # This was not tested...
        return hcipy.Field(final_output.ravel(), focal_grid) / exposure_time, fits.Header()
    else:
        fname = final_output[:-8] + 'bin.fits'

        with fits.open(fname, lazy_load_hdus=False) as hdu:
            header = hdu[0].header
            exp_time = header['EXP_TIME']
            data = hdu[0].data

        return hcipy.Field(data.ravel(), focal_grid) / exp_time, header

take_coron_exposure_hicat = functools.partial(take_exposure_hicat, exposure_type='coron')
take_direct_exposure_hicat = functools.partial(take_exposure_hicat, exposure_type='direct')

def take_pupilcam_hicat(devices,
                        num_exposures=1,
                        exposure_time=1000,
                        file_mode=True,
                        initial_path=None,
                        suffix=None,
                        ):
    """Efficient exposure function using list of device handles already obtained

    Take and save a pupil camera image, without changing DM settings or anything else.

    Assumes you already have handles to all relevant hardware controllers.

    :param devices : dict, Dictionary of device handles for hardware access
    :param num_exposures: number of exposures to take
    :param exposure_time: float, exp time in microsec; set to None to use
           default values set in config.ini for coron or direct modes.
    :param file_mode: Write output to disk if true, else just return the image
    :param initial_path: string, Passed to utils.create_data_path.
    :param suffix: string, Passed to utils.create_data_path.

    :returns: Image in units of counts/sec

    """
    exposure_type =  'pupilcam'
    if suffix is None:
        suffix = exposure_type
    path = hicat.util.create_data_path(initial_path=initial_path, suffix=suffix)

    if file_mode:
        filename = exposure_type + '_image'

        exp_path = os.path.join(path, exposure_type)
        raw_path = os.path.join(exp_path, "raw")
        img_path = os.path.join(raw_path, "images")
    else:
        filename = None

    if exposure_time is not None:
        exposure_time = quantity(exposure_time, units.microsecond)


    # Move beam dump out of the beam
    #devices['beam_dump'].move_to_position2()

    # Take images with imaging_camera
    images, metadata = devices['pupil_camera'].take_exposures(exposure_time, num_exposures,
                                                              file_mode=file_mode,
                                                              raw_skip=0,
                                                              path=img_path,
                                                              filename=filename,
                                                              return_metadata=True)
    return images

#######################################################################################

# FIXME needed the dms to see the probes... I didnt' want to change the interface everywhere so faster to add
#  new function for now. I need the suffix passed too here.
def take_pupilcam_hicat_with_dms(dm1_actuators, dm2_actuators, devices,
                                 num_exposures=1,
                                 exposure_time=120000,
                                 file_mode=True,
                                 initial_path=None,
                                 suffix=None,
                                 ):
    """Efficient exposure function using list of device handles already obtained
    Take and save a pupil camera image, without changing DM settings or anything else.
    Assumes you already have handles to all relevant hardware controllers.
    :param dm1_actuators: DM1 actuator vector, in nm
    :param dm2_actuators: DM2 actuator vector, in nm
    :param devices : dict, Dictionary of device handles for hardware access
    :param num_exposures: number of exposures to take
    :param exposure_time: float, exp time in microsec; set to None to use
           default values set in config.ini for coron or direct modes.
    :param file_mode: Write output to disk if true, else just return the image
    :param initial_path: string, Passed to utils.create_data_path.
    :param suffix: string, Passed to utils.create_data_path.
    :returns: Image in units of counts/sec
    """
    exposure_type = 'pupilcam'
    path = hicat.util.create_data_path(initial_path=initial_path, suffix=suffix)

    dm1_command_object = DmCommand.DmCommand(dm_actuators_to_surface(dm1_actuators * 1e-9).shaped, dm_num=1,
                                             flat_map=True, bias=False)
    dm2_command_object = DmCommand.DmCommand(dm_actuators_to_surface(dm2_actuators * 1e-9).shaped, dm_num=2,
                                             flat_map=True, bias=False)

    if file_mode:
        filename = exposure_type + '_image'

        exp_path = os.path.join(path, exposure_type)
        raw_path = os.path.join(exp_path, "raw")
        img_path = os.path.join(raw_path, "images")
    else:
        filename = None

    if exposure_time is not None:
        exposure_time = quantity(exposure_time, units.microsecond)


    # Move beam dump out of the beam
    #devices['beam_dump'].move_to_position2()

    # Set dm shapes
    devices['dm'].apply_shape_to_both(dm1_command_object, dm2_command_object)

    # Take images with imaging_camera
    # with robustness to flaky pupil camera dropouts
    try:
        images, metadata = devices['pupil_camera'].take_exposures(exposure_time, num_exposures,
                                                                  file_mode=file_mode,
                                                                  raw_skip=0,
                                                                  path=img_path,
                                                                  filename=filename,
                                                                  return_metadata=True)
    except Exception:
        import warnings
        warnings.warn("PUPIL CAMERA EXCEPTION ENCOUNTERED - IGNORING AND CONTINUING")
        images = None

    return images

#######################################################################################


def dm_actuators_to_surface(actuator_vector):
    """ Convert actuator 1D vector to a 2D grid, with zero padding as needed """
    res = hcipy.Field(np.zeros(actuator_grid.size), actuator_grid)
    res[dm_mask] = actuator_vector
    return res


def dm_actuators_from_surface(actuator_surface):
    """ Convert actuator 2D grid to a 1D vector, removing zero padding.
    Inverse of dm_actuators_to_surface
    """
    return actuator_surface.ravel()[dm_mask]


def split_command_vector(actuator_vector, use_dm2):
    """
    Take a vector of DM actuator commands and return the individual command vectors for DM1 and DM2.  This
    accounts for the difference in length (num_actuators vs. 2 * num_actuators) of the vector when running
    single-DM or two-DM control.
    """
    if use_dm2:
        dm1_command = actuator_vector[:num_actuators]
        dm2_command = actuator_vector[num_actuators:]
    else:
        dm1_command = actuator_vector
        dm2_command = np.zeros_like(dm1_command)

    return dm1_command, dm2_command


def calc_jacobian_matrix(dm1_actuators_0, dm2_actuators_0, use_dm2=True,
                         output_filename=None, poke_strength=10):
    """ Calculate Jacobian Matrix (warning - this is SLOW)
    See calc_jacobian_matrix_multiprocess for a faster parallelized version

    :param dm1_actuators_0: DM1 settings around which to linearize
    :param dm2_actuators_0: DM2 settings around which to linearize
    :param use_dm2: bool, True if should model control of both DMs
    :param output_filename: filename to write to
    :param poke_strength: poke strength for each actuator, in nm.
         (output Jacobian is normalized to per nm)

    :returns: FITS.HDUList containing jacobian matrix, which is also written to disk.

    """

    if output_filename is not None and os.path.exists(output_filename):
        raise RuntimeError( "A Jacobian file already exists at the requested filename: {}."
                            "Please use a new filename for this calculation.".format(output_filename))

    # Setup temporary working folder
    jacobian_output_path = hicat.util.create_data_path(suffix='calc_jacobian')
    _setup_simulator_temp_folder(jacobian_output_path)

    # Use a direct exposure to determine normalization of electric fields
    direct, header = take_exposure_hicat_simulator(dm1_actuators_0, dm2_actuators_0, output_path=jacobian_output_path,
                                                   exposure_type='direct')
    norm = np.sqrt(direct.max())

    e0, header = take_exposure_hicat_simulator(dm1_actuators_0, dm2_actuators_0, output_path=jacobian_output_path,
                                               exposure_type='coronEfield')
    e0 /= norm
    jac = np.empty((num_actuators * (2 if use_dm2 else 1), 2 * len(e0)))


    t_start = time.time()
    # Loop through all actuators on DM1
    for i, dm1_actuators in enumerate(np.eye(num_actuators)):
        print("Calculating actuator {} on DM 1".format(i))
        # Calculate electric field and partial derivative for this actuator
        y, header = take_exposure_hicat_simulator(dm1_actuators_0 + poke_strength * dm1_actuators, dm2_actuators_0,
                                                  output_path=jacobian_output_path, exposure_type='coronEfield')
        y /= norm
        y = (y - e0) / poke_strength

        # Add partial derivative to Jacobian matrix
        jac[i, :] = np.concatenate((y.real, y.imag))
        print(i)

    if use_dm2:
        # Loop through all actuators on DM2
        for i, dm2_actuators in enumerate(np.eye(num_actuators)):
            print("Calculating actuator {} on DM 2".format(i))
            y, header = take_exposure_hicat_simulator(dm1_actuators_0, dm2_actuators_0 + poke_strength * dm2_actuators,
                                                      output_path=jacobian_output_path, exposure_type='coronEfield')
            y /= norm
            y = (y - e0) / poke_strength

            jac[num_actuators + i, :] = np.concatenate((y.real, y.imag))
            print(num_actuators + i)
    t_stop = time.time()

    # Save output for future re-use
    if output_filename is None:
        jacobian_filename = 'jacobian_hicat_normalized_%ddm.fits' % ( 2 if use_dm2 else 1)
        output_filename = os.path.join( jacobian_output_path, jacobian_filename)
    return _format_jacobian_output(jac, header, output_filename, poke_strength, use_dm2,
                                   dm1_actuators_0, dm2_actuators_0,
                                   num_processes=1, calctime = t_stop-t_start)


def _format_jacobian_output(jac, header, output_filename, poke_strength, use_dm2, dm1_actuators_0, dm2_actuators_0,
        num_processes=1, calctime=0.0, wavelength=638.0):
    """ Utility function to format Jacobian into FITS file and record metadata.
    Called from both calc_jacobian_matrix and calc_jacobian_matrix_multiprocess
    to consistently format the output.
    """

    # Create output FITS file, reusing header from the image to store details of the calculation setup.
    jac_hdu = fits.PrimaryHDU(jac, header)
    jac_hdu.header['CONTENTS'] = ('Jacobian matrix for HiCAT', "Contents of this file")
    jac_hdu.header['NUM_DMS'] = (2 if use_dm2 else 1, "Number of DMs controlled.")
    jac_hdu.header['POKESTR'] = (poke_strength, "Pole strength in nm")
    jac_hdu.header['FILENAME'] = (os.path.basename(output_filename), 'Original filename')
    jac_hdu.header['SCALE_DM'] = (hicat.simulators.hicat_sim.scale_dm_commands, "Scale factor of 0.5 for DM commands?")
    jac_hdu.header['CALCNPRC'] = (num_processes, "Number of processes used")
    jac_hdu.header['CALCTIME'] = (calctime, "Runtime for this Jacobian calculation")
    jac_hdu.header['WAVELEN'] = (wavelength, "Wavelength in nm")
    # TODO - add more metadata here. Version/git commit id, etc.

    # create second extension containing the DM settings around which this Jacobian is linearized
    dm_hdu = fits.ImageHDU(np.stack((dm1_actuators_0, dm2_actuators_0), axis=0))
    dm_hdu.header['EXTNAME'] = 'DM_SETTINGS'
    dm_hdu.header['CONTENTS'] = ("DM commands around which this Jacobian was linearized.", "Contents of this file")
    dm_hdu.header['BUNIT'] = "nm"

    jacobian_hdulist = fits.HDUList([jac_hdu, dm_hdu])

    print("Writing out Jacobian to " + output_filename)

    jacobian_hdulist.writeto(output_filename)

    return jacobian_hdulist


def _setup_simulator_temp_folder(path):
    """ Set up folder structure to be used by simulator script interface.

    Simulator script interface wants a folder set containing a config.ini and one calibrated image,
    plus optionally DM actuator files. Set up the first part of that here; then later in
    take_exposure_hicat_simulator() it will write the DM files.

    """
    os.makedirs(path, exist_ok=True)
    confdir =  os.path.join(path, 'config')
    os.makedirs(confdir, exist_ok=True)
    conffile = os.path.join(os.path.dirname(hicat.config.__file__), 'config.ini')
    shutil.copy(conffile, os.path.join(confdir, 'config.ini'))
    # Make a nearly-null FITS file, which exists just to provide an exposure time downstream
    tmpfits = fits.PrimaryHDU()
    tmpfits.header['EXP_TIME'] = CONFIG_INI.getfloat('photometry', 'default_exposure_time_simulator_microsec')
    tmpfits.writeto(os.path.join(path, 'temp_cal.fits'), overwrite=True)


def _calc_jacobian_multiprocess_take_e_field_wrapper(dm1_actuators_0, dm2_actuators_0, e0, poke_strength,
                                                     output_path, norm, wavelength, actuator_command_index):
    """ Helper function for multiprocess Jacobian calculations
    In particular multiprocess.pool wants a standalone function we can wrap in functools.partial for pickling,
    in which the last argument is one that we can iterate over

    actuator_command_index counts up from 0 to 951 for DM 1, then 952 onwards for DM 2
    actuator_command_index has to be the last argument so that we can partially apply the others inside of a multiprocessing
    environment

    :returns: complex electric field in the image
    """

    # don't modify input actuator setting arrays:
    dm1_actuators = dm1_actuators_0.copy()
    dm2_actuators = dm2_actuators_0.copy()

    if actuator_command_index < num_actuators:
        dmnum = 1
        act_index = actuator_command_index
    else:
        dmnum = 2
        act_index = actuator_command_index - num_actuators

    print("Calculating actuator {} on DM {}".format(act_index, dmnum))

    # Make a separate working dir for each calculation - needed to avoid multiple
    # processes stepping on each other!
    with tempfile.TemporaryDirectory(suffix="calc_jacobian_temp_{}".format(actuator_command_index)) as jacobian_output_path:
        _setup_simulator_temp_folder(jacobian_output_path)

        # Poke one and only one actuator.
        if dmnum == 1:
            dm1_actuators[act_index] += poke_strength
        else:
            dm2_actuators[act_index] += poke_strength

        # Perform the propagation
        y, header = take_exposure_hicat_simulator(dm1_actuators, dm2_actuators,
                                                  output_path=jacobian_output_path, wavelength=wavelength,
                                                  exposure_type='coronEfield')
        y /= norm
        y = (y - e0) / poke_strength

    return y


def calc_jacobian_matrix_multiprocess(dm1_actuators_0, dm2_actuators_0, use_dm2=True,
                                      output_filename=None, poke_strength=10, wavelength=638.0):
    """ Calculate Jacobian Matrix, parallelized over multiple processes.

    Output should be identical to calc_jacobian_matrix, but the implementation
    is more complex.

    :param dm1_actuators_0: DM1 settings around which to linearize
    :param dm2_actuators_0: DM2 settings around which to linearize
    :param use_dm2: bool, True if should model control of both DMs
    :param output_filename: filename to write to
    :param poke_strength: poke strength for each actuator, in nm.
         (output Jacobian is normalized to per nm)
    :param wavelength: center wavelength at which to compute Jacobian, in nm

    :returns: FITS.HDUList containing jacobian matrix, which is also written to disk.

    """
    import multiprocessing

    if output_filename is not None and os.path.exists(output_filename):
        raise RuntimeError( "A Jacobian file already exists at the requested filename: {}."
                            "Please use a new filename for this calculation.".format(output_filename))

    # Figure out how many processes is optimal and create a Pool.
    # Assume we're the only one on the machine so we can hog all the resources.
    # We expect numpy to use multithreaded math via the Intel MKL library, so
    # we check how many threads MKL will use, and create enough processes so
    # as to use 100% of the CPU cores.
    # You might think we should divide number of cores by 2 to get physical cores
    # to account for hyperthreading, however empirical testing on telserv3 shows that
    # it is slightly more performant on telserv3 to use all logical cores
    num_cpu = multiprocessing.cpu_count()
    # try:
    #     import mkl
    #     # TODO: this is 24 on telserv3, which means we only get 2 processes.  Change this number to something smaller
    #     #   so that we can compute more actuators simultaneously
    #     num_core_per_process = mkl.get_max_threads()
    # except ImportError:
        # typically this is 4, so use that as default
        # log.warning("Couldn't import MKL; guessing default value of 4 cores per process")

    num_core_per_process = 1
    num_processes = int(num_cpu // num_core_per_process)
    print("Multiprocess Jacobian will use {} processes (with {} threads per process)".format(num_processes, num_core_per_process))

    jacobian_output_path = os.path.join(os.path.abspath('.'), 'calc_jacobian_temp_{}'.format(0))
    _setup_simulator_temp_folder(jacobian_output_path)

    direct, header = take_exposure_hicat_simulator(dm1_actuators_0, dm2_actuators_0, output_path=jacobian_output_path,
                                                   wavelength=wavelength, exposure_type='direct')
    contrast_normalization = np.sqrt(direct.max())  # Normalization for electric fields

    e0, header = take_exposure_hicat_simulator(dm1_actuators_0, dm2_actuators_0, output_path=jacobian_output_path,
                                               wavelength=wavelength, exposure_type='coronEfield')
    e0 /= contrast_normalization
    jac = np.empty((num_actuators * (2 if use_dm2 else 1), 2 * len(e0)))

    # Set up a function with all arguments fixed except for actuator number
    calc_jacobian_poke_one = functools.partial(_calc_jacobian_multiprocess_take_e_field_wrapper, dm1_actuators_0, dm2_actuators_0,
                                               e0, poke_strength, jacobian_output_path, contrast_normalization, wavelength)

    # Iterate over all actuators via a multiprocess pool
    mypool = multiprocessing.Pool(num_processes)
    t_start = time.time()
    results = mypool.map(calc_jacobian_poke_one, range(num_actuators*2))
    t_stop = time.time()

    print("Multiprocess calculation complete in {:.1f} s".format(t_stop-t_start))

    # Extract results and store in the format we want.
    for i, y in enumerate(results):
       jac[i, :] = np.concatenate((y.real, y.imag))

    mypool.close()

    # Save output for future re-use
    if output_filename is None:
        jacobian_filename = 'jacobian_hicat_normalized_%ddm.fits' % ( 2 if use_dm2 else 1)
        output_filename = os.path.join( jacobian_output_path, jacobian_filename)

    return _format_jacobian_output(jac, header, output_filename, poke_strength, use_dm2,
                                   dm1_actuators_0, dm2_actuators_0,
                                   wavelength=wavelength,
                                   num_processes=num_processes, calctime = t_stop-t_start)


def calc_probe_actuators(probe_electric_field, jacobian, rcond_probe, use_one_dm_probe=True):
    """

    :param probe_electric_field: 2D ndarray for the desired probe field
    :param jacobian: Jacobian matrix
    :param rcond_probe: conditioning number for the probe calculation in the Tikhonov inversion
    :param use_one_dm_probe: bool, should probe pattern only use DM1?

    :return: actuator vector for both DM1+DM2 (DM2 values may be zero),
             normalized to peak-to-valley=1

    """
    # Use mask to speed up inversion of the Jacobian.
    mask = np.abs(probe_electric_field) > 0.1 * np.abs(probe_electric_field).max()

    # Invert the Jacobian on the mask; use a lot of regularization to keep the probe small.
    # This has the effect of not reproducing the probe electric field in the focal plane very accurately, which
    # is not the goal of this algorithm anyway: we want some electric field relatively close to
    # our dark zone with as little actuator stroke as possible.
    # Sometimes even the first SVD mode might suffice for a probe, but taking a few more modes is
    # safer.
    jacobian_2dm = (jacobian.shape[0] // num_actuators) == 2

    jac = jacobian[:, np.tile(mask, 2)]
    if jacobian_2dm and use_one_dm_probe:
        jac = jac[:num_actuators]

    jac_inv = hcipy.inverse_tikhonov(jac, rcond_probe)

    # Use the inverted Jacobian to transform the probe electric field to an actuator probe
    x = probe_electric_field[mask]
    x = np.concatenate((x.real, x.imag))
    probe = jac_inv.T.dot(x)

    if jacobian_2dm and use_one_dm_probe:
        probe = np.concatenate((probe, np.zeros(num_actuators)))

    # Normalize the probe to 1 ptv
    return probe / np.ptp(probe)


def stroke_min_solver(A, B, mu):
    """
    Find the optimal DM correction for a given Jacobian matrix, electric field estimate, and Lagrange multiplier value.

    :param A: Actuator-to-actuator Jacobian matrix
    :param B: Cross-term between A and electric field estimate
    :param mu: Desired Lagrange multiplier value.
    """
    try:
        correction_dm_actuators = hcipy.inverse_truncated(A + mu * np.eye(A.shape[0])).dot(B)
    except np.linalg.LinAlgError:
        correction_dm_actuators = np.linalg.inv(A + mu * np.eye(A.shape[0])).dot(B)

    return correction_dm_actuators


def compute_stroke_min_quantities(jacobian, electric_field, dark_zone):
    """
    Compute mathematical quantities of interest to the stroke minimization algorithm.

    :param jacobian: Jacobian matrix [num_actuator x  2 * num_pixel]
    :param electric_field: Dark-zone electric field estimate [num_pixel]
    :param dark_zone: focal-plane dark zone mask
    :return:
        M : Jacobian matrix with horizontally-concatenated (real, imaginary) parts. Equivalent to [G.T.real, G.T.imag] in Groff et al.
        b : E-field estimate with concatenated (real, imaginary) parts are concatenated.  Equivalent to [E_ab.T.real, E_ab.T.imag] in Groff et al.
        c : Integrated intensity contrast from E-field estimate.  Equivalent to d in Groff et al.
        A : Inner product of Jacobian with itself.  Equivalent to M.T.real in Groff et al.
        B : Inner product of Jacobian and E-field estimate.  Equivalent to b / 2 in Groff et al.

    Notes
        - In Groff et al., the factor (i 2 * pi / wavelength) is NOT included in the Jacobian matrix, whereas it is included here
        - All matrix quantities are transposed with respect to Groff et al.
    """
    M = jacobian[:, np.tile(dark_zone, 2)]
    b = np.concatenate((electric_field[dark_zone].real, electric_field[dark_zone].imag))

    c = b.dot(b)     # Integrated intensity contrast (coherent part, from E estimate) at previous iteration
    A = M.dot(M.T)   # Actuator-to-actuator Jacobian, integrated over pixels in dark hole
    B = M.dot(b)     # Cross term between the two

    return M, b, c, A, B


def stroke_minimization(jacobian, electric_field, dark_zone, gamma, last_best_mu,
                        mu_step_size=1.3):
    """ Main stroke minimization calculation

    Determine DM corrections to improve contrast by some requested amount, while minimizing
    the total stroke of the requested corrections.

    :param jacobian: Jacobian matrix
    :param electric_field: Electric field, from most recent pairwise sensing
    :param dark_zone: Geometry for region to control
    :param gamma: Desired contrast reduction factor relative to current contrast
    :param last_best_mu: mu used in prior iteration; used to set initial guess mu
    :param mu_step_size: Factor for step size used when adjusting mu.

    :return: tuple containing (vector of DM corrections, best mu,
             predicted contrast at next iteration, predicted change in contrast this iteration)
    """
    normalization = dark_zone.sum()
    M, b, c, A, B = compute_stroke_min_quantities(jacobian, electric_field, dark_zone)
    c /= normalization
    A /= normalization
    B /= normalization
    mu = (mu_step_size ** 2) * last_best_mu

    current_contrast = c
    desired_contrast = gamma * current_contrast
    correction_dm_actuators = np.zeros(num_actuators)

    #log.info('Current contrast:', current_contrast)
    while current_contrast > desired_contrast and mu > 1e-16:
        #log.info('mu:', mu, '; contrast:', current_contrast)
        mu = mu / mu_step_size
        last_dm_actuators = correction_dm_actuators.copy()
        correction_dm_actuators = stroke_min_solver(A, B, mu)
        residual_energy = correction_dm_actuators.dot(A).dot(correction_dm_actuators) - 2 * B.dot(
            correction_dm_actuators) + c                 # Predicted residual after control, i.e. predicted contrast next iteration.
        predicted_contrast_drop = residual_energy - c    # Model prediction for contrast change due to DM control at this iteration.
        last_current_contrast = current_contrast

        current_contrast = residual_energy
        if current_contrast < 0 or current_contrast > 2 * last_current_contrast:
            log.warning("Could not calculate correction (bad contrast) for mu={}; returning results for prior mu.".format(mu))
            return last_dm_actuators, mu
    print("Predicted New Contrast: {}\t".format(residual_energy))

    return correction_dm_actuators, mu, residual_energy, predicted_contrast_drop


def broadband_stroke_minimization(jacobians, electric_fields, dark_zone, gamma, spectral_weights, control_weights,
                                  last_best_mu, mu_step_size=1.3):
    """ Main function for broadband stroke minimization.

    Determine DM corrections to improve contrast by some requested amount, while minimizing
    the total stroke of the requested corrections.

    Assumes two deformable mirrors.

    :param jacobians: Dict of Jacobian matrices (one per wavelength)
    :param electric_fields: Dict of electric field estimates (one per wavelength)
    :param dark_zone: Geometry for region to control
    :param gamma: Desired contrast reduction factor relative to current contrast
    :param spectral weights: Relative intensity at each wavelength, relative to the center wavelength
    :param control_weights: How much to optimize contrast reduction at each wavelength relative to the others
    :param last_best_mu: mu used in prior iteration; used to set initial guess mu
    :param mu_step_size: Factor for step size used when adjusting mu.

    :return: tuple containing (vector of DM corrections, best mu,
             predicted contrast at next iteration, predicted change in contrast this iteration)
    """
    # Stroke minimization algorithm, based on (Mathematica code from Johan Mazoyer, modified by Remi Soummer)
    num_wavelengths = len(jacobians)

    num_pix = dark_zone.sum()
    normalization = num_pix
    A = np.zeros((num_actuators*2, num_actuators*2), dtype=np.float64)  # Assume we have 2 DMs
    B = np.zeros(2 * num_actuators, dtype=np.float64)
    c = 0

    for wavelength in jacobians:
        weight = control_weights[wavelength] * spectral_weights[wavelength]

        if weight:  # Don't bother calculating these quantities if they have zero contribution anyways
            #log.info(f"Calculating stroke min quantities for {wavelength} nm")
            M_n, b_n, c_n, A_n, B_n = compute_stroke_min_quantities(jacobians[wavelength], electric_fields[wavelength], dark_zone)

            A += weight * A_n
            B += weight * B_n
            c += weight * c_n

    A /= normalization
    B /= normalization
    c /= normalization

    mu = (mu_step_size ** 2) * last_best_mu

    current_contrast = c
    desired_contrast = gamma * current_contrast
    correction_dm_actuators = np.zeros(num_actuators)

    #log.info('Calculating corrections:')
    #log.info('Current contrast:', current_contrast)
    while current_contrast > desired_contrast and mu > 1e-16:
        #log.info('mu:', mu, '; contrast:', current_contrast)
        mu = mu / mu_step_size
        last_dm_actuators = correction_dm_actuators.copy()
        correction_dm_actuators = stroke_min_solver(A, B, mu)
        residual_energy = correction_dm_actuators.dot(A).dot(correction_dm_actuators) - 2 * B.dot(
            correction_dm_actuators) + c                 # Predicted residual after control, i.e. predicted contrast next iteration.
        predicted_contrast_drop = residual_energy - c    # Model prediction for contrast change due to DM control at this iteration.
        last_current_contrast = current_contrast

        current_contrast = residual_energy
        if current_contrast < 0 or current_contrast > 2 * last_current_contrast:
            log.warning("Could not calculate correction (bad contrast) for mu={}; returning results for prior mu.".format(mu))
            return last_dm_actuators, mu
    #log.info("Predicted New Contrast: {}\t".format(residual_energy))

    return correction_dm_actuators, mu, residual_energy, predicted_contrast_drop


def electric_field_conjugation(jacobian, electric_field, dark_zone, rcond):
    """ Electric Field Conjucation control algorithm

    :param jacobian:  Jacobian
    :param electric_field: Electric field as measured by sensing
    :param dark_zone: mask for dark zone geometry on focal grid
    :param rcond: regularization parameter for inverse tikhonov
    :return:
    """
    G = jacobian[:, np.tile(dark_zone, 2)]
    inv_G = hcipy.inverse_tikhonov(G, rcond)

    correction = inv_G.dot(np.concatenate((electric_field[dark_zone].real, electric_field[dark_zone].imag)))
    return correction


def calculate_observation_matrix(probes, dark_zone, rcond, use_dm2=True, output_filename=None, wavelength=638.0):
    """Calculate observation matrix for given set of probes;
    mapping from the applied probe vectors to the changes in E field within the
    dark zone region.

    :param probes: List of probe vectors
    :param wavelength: imaging wavelength, in nm
    :param dark_zone: mask for dark zone geometry on focal grid
    :param rcond: regularization parameter for inverse tikhonov
    :param output_filename: where to write output file

    :returns: observation matrix, which is also written to disk
    """

    obsmatrix_output_path = hicat.util.create_data_path(suffix='calc_obs_matrix')
    _setup_simulator_temp_folder(obsmatrix_output_path)

    dm1_actuators_0 = np.zeros(num_actuators)
    dm2_actuators_0 = np.zeros(num_actuators)

    # Normalize all electric fields using normalized irradiance.
    direct_image, header = take_exposure_hicat_simulator(dm1_actuators_0, dm2_actuators_0,
                                                         output_path=obsmatrix_output_path, wavelength=wavelength,
                                                         exposure_type='direct')
    norm = np.sqrt(direct_image.max())

    H = []

    # Use full propagation from the simulator here, instead of using the jacobian.
    # This will include non-linear effects from the probes, but requires the
    # gain of the DM (voltage to stroke) to be well determined.
    for p in probes:
        use_dm2 = (len(p) // num_actuators) == 2
        p1, p2 = split_command_vector(p, use_dm2)

        E_pos, header_pos = take_exposure_hicat_simulator(dm1_actuators_0 + p1, dm2_actuators_0 + p2,
                                                          output_path=obsmatrix_output_path, wavelength=wavelength,
                                                          exposure_type='coronEfield')
        E_neg, header_neg = take_exposure_hicat_simulator(dm1_actuators_0 - p1, dm2_actuators_0 - p2,
                                                          output_path=obsmatrix_output_path, wavelength=wavelength,
                                                          exposure_type='coronEfield')

        E_pos /= norm
        E_neg /= norm

        E_delta = (E_pos - E_neg)
        H.append([E_delta.real, E_delta.imag])

    # Accumulate all tensors in a tensor hcipy.Field
    H = 2 * hcipy.Field(H, focal_grid)

    # Invert the tensors for each pixel with regularization
    # to get the observation matrix.
    H_inv = hcipy.field_inverse_tikhonov(H, rcond)[..., dark_zone]
    # Dimensions of H_inv are [probe index, real/imag, pixel index within dark zone]

    # Save output for future re-use
    if output_filename is None:
        obsmatrix_filename = 'H_inv_normalized_%ddm.fits' % (2 if use_dm2 else 1)
        output_filename = os.path.join( obsmatrix_output_path, obsmatrix_filename)
    print("Writing out Observation Matrix to " + output_filename)

    # Create output FITS file, reusing header from the image to store details of the calculation setup.
    H_inv_hdu = fits.PrimaryHDU(np.array(H_inv), header)
    H_inv_hdu.header['CONTENTS'] = ('Observation Matrix inverse for HiCAT', "Contents of this file")
    H_inv_hdu.header['EXTNAME'] = 'OBS_MATRIX'
    H_inv_hdu.header['NUM_DMS'] = (2 if use_dm2 else 1, "Number of DMs controlled.")
    H_inv_hdu.header['RCOND'] = (rcond, "Regularization Parameter")
    H_inv_hdu.header['FILENAME'] = (os.path.basename(output_filename), 'Original filename')
    H_inv_hdu.writeto(output_filename)
    #hcipy.write_fits(np.array(H_inv), output_filename)

    # TODO should also record a copy of input parameters here here as well?
    # probes, dark_zone, rcond

    return H_inv


def take_electric_field_pairwise(dm1_actuators_0, dm2_actuators_0, take_image, devices, H_inv, probes, dark_zone,
                                 direct_image, current_contrast=None, probe_amplitude=None, fudge_factor_to_see_probe=1,
                                 initial_path=None, include_pupil_images=False, wavelength=638.0):
    """Calculate E field via pairwise probe images

    Iterate over probes, apply to DM(s), take images using the testbed hardware,
    calculate E field and return.

    Optionally, the amplitude of the probes can be auto-scaled based on the current contrast.
    To use this feature, provide the current_contrast and probe_amplitude parameters.
    The scaling follows the rule-of-thumb ~ 10 * wavelength * sqrt(contrast)
    NOTE, currently the wavelength is hard-coded to 638 nm for HiCAT, which is sufficient for
    current purposes but could be revisited when we start broadband control.

    :param dm1_actuators_0: DM actuator vectors without any probes applied.
    :param dm2_actuators_0: DM actuator vectors without any probes applied.
    :param take_image: Function handle to take images.
    :param devices: dict of device controllers
    :param H_inv: inverse of observation matrix for those probes
    :param probes: List of probes
    :param dark_zone: Geometry of dark zone
    :param direct_image: Most recent direct image, used for contrast normalization of probe results.
                         Must be in units of counts/second.
    :param fudge_factor_to_see_probe: this is used for the pupil images.  Because the probes are too faint to see so
    this is multipled by the fudge factor
    :param initial_path: path where to write the pupil images.  Set to None by default becasue it's only used for the
    pupil imaging as part of the run_pairwise.py for now.
    :param current_contrast: Most recent estimated contrast, for auto scaling of probe amplitude.
    :param probe_amplitude: Default amplitude of the probes, in nanometers. Provides the reference
                         starting point for probe amplitude scaling.

    :return: Tuple with (E, probe_example)
             E = Electric field, in units of sqrt(contrast), over the focal grid, but
             with nonzero values only in the dark zone.
             probe_example = One representative probe image
    """
    I_deltas = []

    if current_contrast is not None:
        # target probe amplitude is notionally 10*lambda*sqrt(contrast)
        # but aim 2x higher than that for a bit more modulation strength
        # FIXME consider passing in wavelength too, if we eventually want this to scale vs. wavelength for broadband sensing
        desired_amplitude = 20 * wavelength * 1e-9 * np.sqrt(current_contrast)
        default_amplitude = probe_amplitude * 1e-9  # convert from nm to m
        probe_amp_scaling = min(desired_amplitude / default_amplitude, 1) # only scale probes down, not up, from starting amplitude
        log.info("Probe amplitude scaling: for desired probe amplitude {}, will use scale factor {}".format(desired_amplitude, probe_amp_scaling))
    else:
        probe_amp_scaling = 1.0

    # Collect delta intensity images for each probe.
    for i, probe in enumerate(probes):
        p = probe * probe_amp_scaling  # Scale to get desired amplitude ratio, don't modify input arrays
        use_dm2 = (len(p) // num_actuators) == 2
        p1, p2 = split_command_vector(p, use_dm2)
        suffix = "probe_{}".format(i)

        I_pos, header_pos = take_image(dm1_actuators_0 + p1, dm2_actuators_0 + p2,
                                       suffix=suffix + "_pos", wavelength=wavelength)
        I_pos /= direct_image.max()

        if include_pupil_images:
            take_pupilcam_hicat_with_dms(fudge_factor_to_see_probe * (dm1_actuators_0 + p1), dm2_actuators_0 + p2, devices,
                                         initial_path=initial_path, suffix=suffix + "_pos_pupil")

        I_neg, header_neg = take_image(dm1_actuators_0 - p1, dm2_actuators_0 - p2,
                                       suffix=suffix + "_neg", wavelength=wavelength)

        I_neg /= direct_image.max()

        if include_pupil_images:
            take_pupilcam_hicat_with_dms(fudge_factor_to_see_probe * (dm1_actuators_0 - p1), dm2_actuators_0 - p2, devices,
                                     initial_path=initial_path, suffix=suffix + "_neg_pupil")

        I_deltas.append((I_pos - I_neg)[dark_zone])

    I_deltas = hcipy.Field(np.array(I_deltas), focal_grid)

    # Mutiply the observation matrix by the intensity differences for each pixel.
    E = hcipy.Field(np.zeros(focal_grid.size, dtype='complex'), focal_grid)
    y = hcipy.field_dot(hcipy.Field(H_inv / probe_amp_scaling, focal_grid), I_deltas)

    # Rebuild electric field from the vector hcipy.Field, and put into dark zone pixels.
    E[dark_zone] = y[0, :] + 1j * y[1, :]

    return E, I_pos


