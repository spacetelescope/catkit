import time
import os

from catkit.hardware.iris_ao import segmented_dm_command
import catkit.hardware.iris_ao.util as iris_util
from hicat.config import CONFIG_INI
from hicat.hardware import testbed
import hicat.util


def flat_command():
    """
    Return a catkit SegmentedDmCommand() object containing only the custom flat command.
    """
    dm_config_id = CONFIG_INI.get("testbed", 'iris_ao')
    repo_root = hicat.util.find_repo_location()
    iris_filename_flat = os.path.join(repo_root, CONFIG_INI.get(dm_config_id, 'custom_flat_file_ini'))

    command_flat = segmented_dm_command.load_command(zero_array(nseg=37)[0],
                                                     dm_config_id,
                                                     640,
                                                     "testbed",
                                                     apply_flat_map=True,
                                                     filename_flat=iris_filename_flat)
    return command_flat


def none_command():
    """
    Create a command from None, will contain all zeros as command.
    :return: list of tuples for DM command, string for command name
    """
    command_to_load = None    # Load zeros, if flat_map=True, will just be flat
    command_str = f'default_flat'

    return command_to_load, command_str


def flat_map_4d(flat_command_file):
    """
    Create a command from the 4D flat
    :param flat_command_file: catkit.hardware.iris_ao.segmented_dm_command.SegmentedDmCommand
    :return: list of tuples for DM command, string for command name
    """
    command_to_load = flat_command_file
    command_str = f'4d_flat'

    return command_to_load, command_str


def image_array(image_array_command_file):
    """
    Create a command of the Image Array configuration, which assumes a radially symmetric tip/tilt
    on each segment, moving each subPSF radially outward.
    :param image_array_command_file: catkit.hardware.iris_ao.segmented_dm_command.SegmentedDmCommand
    :return: list of tuples for DM command, string for command name
    """
    command_to_load = image_array_command_file
    command_str = f'image_array'

    return command_to_load, command_str


def command_from_zernikes(dm_config_id, wavelength, global_coefficients=[0., 0., 0., 2e-7]):
    """
    Create a command from Poppy using global coefficents
    :param dm_config_id: str, name of the section in the config_ini file where information
                         regarding the segmented DM can be found.
    :param wavelength: float, wavelength in nm of the poppy optical system used for
                       (extremely oversimplified) focal plane simulations
    :param global_coefficients: list of global zernike coefficients in the form
                                [piston, tip, tilt, defocus, ...] (Noll convention)
                                in meters of optical path difference (not waves)
    :return: list of tuples for DM command, string for command name
    """
    poppy_command = segmented_dm_command.PoppySegmentedCommand(global_coefficients,
                                                               dm_config_id=dm_config_id,
                                                               wavelength=wavelength)
    command_to_load = poppy_command.to_dm_list()
    command_str = f'poppy_defoc'

    return command_to_load, command_str


def zero_array(nseg):
    """
    Create a zero array, which can be passed to a sgmented DM command.
    :return: list of tuples for DM command, string for command name
    """
    command_to_load = iris_util.create_zero_list(nseg)
    command_str = f'zeros'

    return command_to_load, command_str


def letter_f(dm_config_id, testbed_config_id, filename_flat, wavelength):
    """
    Create a letter F command for the IrisAO
    :param dm_config_id: str, name of the section in the config_ini file where information
                         regarding the segmented DM can be found.
    :param testbed_config_id: str, name of the section in the config_ini file where information
                              regarding the testbed can be found.
    :param filename_flat: str, full path to the custom flat map
    :param wavelength: float, wavelength in nm of the poppy optical system used for
                       (extremely oversimplified) focal plane simulations
    :return: list of tuples for DM command, string for command name
    """
    letter_f_command = segmented_dm_command.SegmentedDmCommand(dm_config_id=dm_config_id,
                                                               wavelength=wavelength,
                                                               testbed_config_id=testbed_config_id,
                                                               filename_flat=filename_flat)
    letter_f_segments = [18, 6, 5, 14, 8, 0]
    for i in letter_f_segments:
        letter_f_command.update_one_segment(i, (0, 2, 0), add_to_current=True)

    command_to_load = letter_f_command.data
    command_str = f'letter_f'

    return command_to_load, command_str


def place_command_on_iris_ao(dm_config_id, command_str='', iris_command=None, seconds_to_hold_shape=10,
                             apply_flat=True, verbose=False):
    """
    Most basic function that puts a shape on the DM and holds that shape for a specified number of second
    :param dm_config_id: str, name of the section in the config_ini file where information
                         regarding the segmented DM can be found.
    :param command_str: str, name of command (currently not used in this function)
    :param iris_command: catkit.hardware.iris_ao.segmented_dm_command.SegmentedDmCommand
    :param seconds_to_hold_shape: float, how many seconds to hold the command before releasing
    :param apply_flat: bool, whether to also apply the custom flat or not
    :param verbose: bool, whether to print out the command put on the IrisAO or not
    """
    print("Flat map will {}be applied".format("not " if not apply_flat else ""))

    with testbed.iris_ao(dm_config_id) as iris:
        iris.apply_shape(iris_command)

        if verbose:
            print("Command before flat map is applied: {}".format(iris_command.get_data()))

        time.sleep(seconds_to_hold_shape)  # Wait while holding shape on DM


def run_one_command(dm_config_id, testbed_config_id, apply_flat_map, filename_flat, command_to_load, command_str,
                    wavelength, seconds_to_hold_shape=10, simulation=False, verbose=False, out_dir=''):
    """
    Load one command on the DM and hold shape for specified time. Can also
    save out expected simulated images.
    :param dm_config_id: str, name of the section in the config_ini file where information
                         regarding the segmented DM can be found.
    :param testbed_config_id: str, name of the section in the config_ini file where information
                              regarding the testbed can be found.
    :param apply_flat_map: bool, whether to also apply the custom flat or not
    :param filename_flat: str, full path to the custom flat map
    :param command_to_load: catkit.hardware.iris_ao.segmented_dm_command.SegmentedDmCommand
    :param command_str: str, name of command
    :param wavelength: float, wavelength in nm of the poppy optical system used for
                       (extremely oversimplified) focal plane simulations
    :param seconds_to_hold_shape: float, how many seconds to hold the command before releasing
    :param simulation: bool, whether to save out what the simulator thinks we will see on
                       the DM or in an imaging camera
    :param verbose: bool, whether to print out the command put on the IrisAO or not
    :param out_dir: str, where to save out any sim files
    """
    iris_command = segmented_dm_command.load_command(command_to_load, dm_config_id,
                                                     wavelength, testbed_config_id,
                                                     apply_flat_map=apply_flat_map,
                                                     filename_flat=filename_flat)
    if simulation:
        iris_command.display(display_wavefront=True, display_psf=True,
                             psf_rotation_angle=90, figure_name_prefix=command_str, out_dir=out_dir)

    place_command_on_iris_ao(dm_config_id=dm_config_id, command_str=command_str, iris_command=iris_command,
                             seconds_to_hold_shape=seconds_to_hold_shape, apply_flat=apply_flat_map, verbose=verbose)


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

        place_command_on_iris_ao(dm_config_id=dm_config_id, command_str=command_str, iris_command=iris_command,
                                 seconds_to_hold_shape=seconds_to_hold_shape, apply_flat=apply_flat_map, verbose=verbose)