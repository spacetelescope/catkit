import time
import os

from catkit.hardware.iris_ao import segmented_dm_command
import catkit.hardware.iris_ao.util as iris_util
from hicat.config import CONFIG_INI
from hicat.hardware import testbed
import hicat.util


class HicatSegmentedDmCommand(segmented_dm_command.SegmentedDmCommand):
    """Subclass of SegmentedDmCommand with correct default values for HICAT

    This sets the dm_config_id and filename_flat values by default to the values
    in the HICAT config file. You can optionally still override those by setting the
    parameters if you want, but for typical HICAT usage you should not have to do so.

    The point of this class is to avoid having to manually pass around the default values
    for dm_config_id, apply_flat_map, and so on, into all of the segmented DM command functions.
    """
    def __init__(self, dm_config_id=None, rotation=0, display_wavelength=640, apply_flat_map=True, filename_flat=None):
        if dm_config_id is None:
            dm_config_id = CONFIG_INI.get('testbed', 'iris_ao')
        repo_root = hicat.util.find_repo_location()
        if filename_flat is None:
            filename_flat = os.path.join(repo_root, CONFIG_INI.get(dm_config_id,
                                                                   'custom_flat_file_ini'))  # Path to the 4D flat for this DM
        super().__init__(dm_config_id, rotation=rotation, display_wavelength=display_wavelength,
                         apply_flat_map=apply_flat_map, filename_flat=filename_flat)


def flat_command():
    """ Return a catkit SegmentedDmCommand() object to flatten the segmented DM

    :return: Segmented DM command object
    """
    return HicatSegmentedDmCommand()


def image_array(image_array_command_file):
    """
    Create a command of the Image Array configuration, which assumes a radially symmetric tip/tilt
    on each segment, moving each subPSF radially outward.
    :param image_array_command_file: catkit.hardware.iris_ao.segmented_dm_command.SegmentedDmCommand
    :return: list of tuples for DM command, string for command name
    """
    command_to_load = image_array_command_file
    # TODO - shouldn't this function do more than just return a provided filename?!
    return command_to_load


def command_from_zernikes(global_coefficients=[0., 0., 0., 2e-7]):
    """ Create a command using global Zernike coefficents to set the shape of the segmented DM

    :param coefficients: list of global zernike coefficients in the form
                                [piston, tip, tilt, defocus, ...] (Noll convention)
                                in meters of optical path difference (not waves)
    :return: Segmented DM command object
    """
    hicat_command = HicatSegmentedDmCommand()   # used only to get the relevant hicat default parameters
                                                # which we pass into this call to create the desired command:
    zernike_command = segmented_dm_command.PoppySegmentedDmCommand(global_coefficients,
                                                                   dm_config_id=hicat_command.dm_config_id,
                                                                   display_wavelength=hicat_command.display_wavelength,
                                                                   apply_flat_map=hicat_command.apply_flat_map,
                                                                   filename_flat=hicat_command.filename_flat)
    return zernike_command


def zero_array(nseg=37):
    """
    Create a zero array, which can be passed to a sgmented DM command.
    :return: list of tuples for DM command, string for command name
    """
    return iris_util.create_zero_list(nseg)


def letter_f():
    """ Return a letter F command for the IrisAO segmented DM

    :param dm_config_id: str, name of the section in the config_ini file where information
                         regarding the segmented DM can be found.
    :param testbed_config_id: str, name of the section in the config_ini file where information
                              regarding the testbed can be found.
    :param filename_flat: str, full path to the custom flat map
    :param wavelength: float, wavelength in nm of the poppy optical system used for
                       (extremely oversimplified) focal plane simulations
    :return: Segmented DM command object
    """
    letter_f_command = HicatSegmentedDmCommand()
    letter_f_segments = [18, 6, 5, 14, 8, 0]
    for i in letter_f_segments:
        letter_f_command.update_one_segment(i, (0, 2, 0), add_to_current=True)
    return letter_f_command


def place_command_on_iris_ao(iris_command=None, seconds_to_hold_shape=10,
                             verbose=False):
    """
    Most basic function that puts a shape on the DM and holds that shape for a specified number of second
    :param iris_command: catkit.hardware.iris_ao.segmented_dm_command.SegmentedDmCommand
    :param seconds_to_hold_shape: float, how many seconds to hold the command before releasing
    :param apply_flat: bool, whether to also apply the custom flat or not
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
                             psf_rotation_angle=90, figure_name_prefix=command_str, out_dir=out_dir)

    place_command_on_iris_ao(iris_command=iris_command,
                             seconds_to_hold_shape=seconds_to_hold_shape,  verbose=verbose)


def kick_out_all_segments(nseg, dm_config_id, testbed_config_id, filename_flat, out_dir, image_array_command_file,
                          wavelength, seconds_to_hold_shape=10, simulation=False, verbose=False):
    """
    In an Image Array configuration, move all segments individually and take images
    :param nseg: int, total number of active segments in the pupil
    :param dm_config_id: str, name of the section in the config_ini file where information
                         regarding the segmented DM can be found.
    :param testbed_config_id: str, name of the section in the config_ini file where information
                              regarding the testbed can be found.
    :param filename_flat: str, full path to the custom flat map
    :param out_dir: str, where to save out any sim files
    :param image_array_command_file: catkit.hardware.iris_ao.segmented_dm_command.SegmentedDmCommand
    :param wavelength: float, wavelength in nm of the poppy optical system used for
                       (extremely oversimplified) focal plane simulations
    :param seconds_to_hold_shape: float, how many seconds to hold the command before releasing
    :param simulation: bool, whether to save out what the simulator thinks we will see on
                       the DM or in an imaging camera
    :param verbose: bool, whether to print out the command put on the IrisAO or not
    """
    apply_flat_map = True
    command_to_load, command_str = image_array(image_array_command_file)
    iris_command = segmented_dm_command.load_command(command_to_load, dm_config_id,
                                                     wavelength, testbed_config_id,
                                                     apply_flat_map=apply_flat_map,
                                                     filename_flat=filename_flat)
    for i in range(nseg):
        iris_command.update_one_segment(i, (0.0, 5.0, 0.0))
        command_str = f'{command_str}_move_seg{i}'

        if simulation:
            iris_command.display(display_wavefront=True, display_psf=True,
                                 psf_rotation_angle=90, figure_name_prefix=command_str, out_dir=out_dir)

        place_command_on_iris_ao(iris_command=iris_command,
                                 seconds_to_hold_shape=seconds_to_hold_shape,  verbose=verbose)