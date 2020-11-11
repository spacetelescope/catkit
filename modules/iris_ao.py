import time
import os

import astropy.units as u
from catkit.hardware.iris_ao import segmented_dm_command
from hicat.config import CONFIG_INI
from hicat.hardware import testbed
import hicat.util

# Functions for interacting with the IrisAO Deformable Mirrors, particularly control commands.
#
# The following functions are mostly conveniences for easily making typical commands we might
# want to send to the Iris DM on HiCAT. See catkit's segmented_dm_commands.py for the full interface.
#
# TODO: Add function(s) to decompose a wavefront as measured by pairwise sensing on HICAT into a
#       control command for the segmented DM.


class HicatSegmentedDmCommand(segmented_dm_command.SegmentedDmCommand):
    """Subclass of SegmentedDmCommand with correct default values for HiCAT

    This sets the dm_config_id and filename_flat values by default to the values
    in the HiCAT config file. You can optionally still override those by setting the
    parameters if you want, but for typical HiCAT usage you should not have to do so.

    The point of this class is to avoid having to manually pass around the default values
    for dm_config_id, apply_flat_map, and so on, into all of the segmented DM command functions.
    """
    def __init__(self, dm_config_id=None, rotation=0, apply_flat_map=True, filename_flat=None):
        if dm_config_id is None:
            dm_config_id = CONFIG_INI.get('testbed', 'iris_ao')
        repo_root = hicat.util.find_repo_location()
        if filename_flat is None:
            filename_flat = os.path.join(repo_root, CONFIG_INI.get(dm_config_id,
                                                                   'custom_flat_file_ini'))  # Path to the 4D flat for this DM
        super().__init__(dm_config_id, rotation=rotation,
                         apply_flat_map=apply_flat_map, filename_flat=filename_flat)

    def plot_psf(self, wavelength=640*u.nm, pixelscale=None, instrument_fov=None, *args, **kwargs):
        # Initialize parameters for displaying the command
        if instrument_fov is None:
            instrument_fov = CONFIG_INI.getint(self.dm_config_id, 'fov_irisao_plotting')
        if pixelscale is None:
            pixelscale = CONFIG_INI.getfloat(self.dm_config_id, 'pixelscale_iriso_plotting')
        super().plot_psf(wavelength=wavelength, pixelscale=pixelscale, instrument_fov=instrument_fov, *args, **kwargs)


def flat_command():
    """ Return a catkit SegmentedDmCommand() object to flatten the segmented DM

    :return: Segmented DM command object
    """
    return HicatSegmentedDmCommand()


def command_from_zernikes(global_coefficients=[0., 0., 0., 2e-7]):
    """ Create a command using global Zernike coefficents to set the shape of the segmented DM

    :param global_coefficients: list of global zernike coefficients in the form
                                [piston, tip, tilt, defocus, ...] (Noll convention)
                                in meters of optical path difference (not waves)
    :return: Segmented DM command object
    """
    hicat_command = HicatSegmentedDmCommand()   # used only to get the relevant HiCAT default parameters
                                                # which we pass into this call to create the desired command:
    zernike_command = segmented_dm_command.PoppySegmentedDmCommand(global_coefficients,
                                                                   dm_config_id=hicat_command.dm_config_id,
                                                                   apply_flat_map=hicat_command.apply_flat_map,
                                                                   filename_flat=hicat_command.filename_flat)
    hicat_command.read_initial_command(zernike_command.to_dm_list())  # cast back into the HiCAT-specific class to have
                                                                      # the overridden display function
    return hicat_command


def letter_f(axis=1, amplitude=2):
    """ Return a letter F command for the IrisAO segmented DM

    :param axis: Which axis (0=piston, 1=tip, 2=tilt) to make the letter F using.
           By default the F is made up of segments with tip on them (axis=1).
    :param amplitude: Amplitude of the letter F, in the control units for that
           axis (um for piston, mrad for tip/tilt).

    :return: Segmented DM command object
    """
    letter_f_command = HicatSegmentedDmCommand()
    letter_f_segments = [18, 6, 5, 14, 8, 0]
    ptt_values = tuple(amplitude if i == axis else 0 for i in range(3))
    for i in letter_f_segments:
        letter_f_command.update_one_segment(i, ptt_values, add_to_current=True)
    return letter_f_command


def poke_one_segment(segment_ind, piston=1.0):
    """ Return a command that pokes one segment by the specified amount

    :param segment_ind: index of which segment to poke
    :param piston: float, amount of piston in control units (microns)
    """
    poke_command = HicatSegmentedDmCommand()
    poke_command.update_one_segment(segment_ind, (piston, 0, 0))
    return poke_command


def tilt_one_segment(segment_ind, tip=0, tilt=0):
    """ Return a command that tilts one segment by the specified amount

    :param segment_ind: index of which segment to poke
    :param tip: float, amount of tip in control units (mrad)
    :param tilt: float, amount of tilt in control units (mrad)
    """
    tt_command = HicatSegmentedDmCommand()
    tt_command.update_one_segment(segment_ind, (0, tip, tilt))
    return tt_command


def place_command_on_iris_ao(iris_command=None, seconds_to_hold_shape=10,
                             verbose=False):
    """
    Most basic function that puts a shape on the DM and holds that shape for a specified number of second
    :param iris_command: catkit.hardware.iris_ao.segmented_dm_command.SegmentedDmCommand
    :param seconds_to_hold_shape: float, how many seconds to hold the command before releasing
    :param verbose: bool, whether to print out the command put on the IrisAO or not
    """

    with testbed.iris_ao() as iris:
        iris.apply_shape(iris_command)

        if verbose:
            print("Command before flat map is applied: {}".format(iris_command.get_data()))

        time.sleep(seconds_to_hold_shape)  # Wait while holding shape on DM


def run_one_command(command_to_load, command_str, seconds_to_hold_shape=10, simulation=False, verbose=False, out_dir=''):
    """
    Load one command on the DM and hold shape for specified time. Can also
    save out expected simulated images.

    :param command_to_load: catkit.hardware.iris_ao.segmented_dm_command.SegmentedDmCommand
    :param command_str: str, name of command. Used in output file names
    :param seconds_to_hold_shape: float, how many seconds to hold the command before releasing
    :param simulation: bool, whether to save out what the simulator thinks we will see on
                       the DM or in an imaging camera
    :param verbose: bool, whether to print out the command put on the IrisAO or not
    :param out_dir: str, where to save out any sim files
    """

    if not isinstance(command_to_load, segmented_dm_command.SegmentedDmCommand):
        raise TypeError("Command must be an instance of SegmentedDmCommand")
    else:
        iris_command = command_to_load

    if verbose:
        print(f"Applying {command_str} command with the values:{command_to_load.data}")

    if simulation:
        if verbose:
            print(f"All output files will be saved to {out_dir}")
        iris_command.display(display_wavefront=True, display_psf=True,
                             psf_rotation_angle=0, figure_name_prefix=command_str, out_dir=out_dir)

    place_command_on_iris_ao(iris_command=iris_command,
                             seconds_to_hold_shape=seconds_to_hold_shape,  verbose=verbose)
