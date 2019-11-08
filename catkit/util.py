import datetime
import importlib
import os
import logging
import logging.handlers
import time

import numpy as np
from astropy.io import fits

from hicat.config import CONFIG_INI

def find_package_location(package='catkit'):
    return importlib.util.find_spec(package).submodule_search_locations[0]


def find_repo_location(package='cakit'):
    return os.path.abspath(os.path.join(find_package_location(package), os.pardir))


def get_dm_mask():
    mask_path = os.path.join(find_package_location("catkit"), "hardware", "boston", "kiloCdm_2Dmask.fits")
    mask = fits.open(mask_path)[0].data
    return mask


def convert_dm_command_to_image(dm_command):
    # Flatten the mask using index952
    mask = get_dm_mask()
    index952 = np.flatnonzero(mask)

    number_of_actuators_per_dimension = CONFIG_INI.getint('boston_kilo952', 'dm_length_actuators')
    number_of_actuators = CONFIG_INI.getint("boston_kilo952", "number_of_actuators")
    image = np.zeros((number_of_actuators_per_dimension, number_of_actuators_per_dimension))
    image[np.unravel_index(index952, image.shape)] = dm_command[:number_of_actuators]

    return image


def convert_dm_image_to_command(dm_image, path_to_save=None):
    # Flatten the gain_map using index952
    mask = get_dm_mask()
    index952 = np.flatnonzero(mask)

    # Parse using index952.
    image_1d = np.ndarray.flatten(dm_image)
    dm_command = image_1d[index952]

    # Write new image as fits file
    if path_to_save is not None:
        write_fits(dm_command, path_to_save)
    return dm_command

# Does numpy gotchu?
def safe_divide(a, b):
    """ ignore / 0, div0( [-1, 0, 1], 0 ) -> [0, 0, 0] """
    with np.errstate(divide='ignore', invalid='ignore'):
        c = np.true_divide(a, b)
        c[~ np.isfinite(c)] = 0  # -inf inf NaN
    return c


def write_fits(data, filepath, header=None, metadata=None):
    """
    Writes a fits file and adds header and metadata when necessary.
    :param data: numpy data (aka image)
    :param filepath: path to save the file, include filename.
    :param header: astropy hdu.header.
    :param metadata: list of MetaDataEntry objects that will get added to header.
    :return: filepath
    """
    log = logging.getLogger()
    # Make sure file ends with fit or fits.
    if not (filepath.endswith(".fit") or filepath.endswith(".fits")):
        filepath += ".fits"

    if not os.path.exists(os.path.dirname(filepath)):
        os.makedirs(os.path.dirname(filepath))

    # Create a PrimaryHDU object to encapsulate the data.
    hdu = fits.PrimaryHDU(data)
    if header is not None:
        hdu.header = header

    # Add metadata to header.
    if metadata is not None:
        for entry in metadata:
            if len(entry.name_8chars) > 8:
                log.warning("Fits Header Keyword: " + entry.name_8chars +
                      " is greater than 8 characters and will be truncated.")
            if len(entry.comment) > 47:
                log.warning("Fits Header comment for " + entry.name_8chars +
                      " is greater than 47 characters and will be truncated.")
            hdu.header[entry.name_8chars[:8]] = (entry.value, entry.comment)

    # Create a HDUList to contain the newly created primary HDU, and write to a new file.
    fits.HDUList([hdu])
    hdu.writeto(filepath, overwrite=True)

    log.info("Wrote " + filepath)
    return filepath


def rotate_and_flip_image(data, theta, flip):
    """
    Converts an image based on rotation and flip parameters.
    :param data: Numpy array of image data.
    :param theta: Rotation in degrees of the mounted camera, only these discrete values {0, 90, 180, 270}
    :param flip: Boolean for whether to flip the data using np.fliplr.
    :return: Converted numpy array.
    """
    data_corr = np.rot90(data, int(theta / 90))

    if flip:
        data_corr = np.fliplr(data_corr)

    return data_corr


def create_flatmap_from_dm_command(dm_command_path, output_path, file_name=None, dm_num=1):
    """
    Converts a dm_command_2d.fits to the format used for the flatmap, and outputs a new flatmap fits file.
    :param dm_command_path: Full path to the dm_command_2d.fits file.
    :param output_path: Path to output the new flatmap fits file. Default is hardware/boston/
    :param file_name: Filename for new flatmap fits file. Default is flatmap_<timestamp>.fits
    :return: None
    """
    dm_command_data = fits.getdata(dm_command_path)

    dm_string = "dm1" if dm_num == 1 else "dm2"

    if file_name is None:
        # Create a string representation of the current timestamp.
        time_stamp = time.time()
        date_time_string = datetime.datetime.fromtimestamp(time_stamp).strftime("%Y-%m-%dT%H-%M-%S")
        file_name = "flat_map_volts_" + str(dm_string) + "_" + date_time_string + ".fits"

    if output_path is None:
        raise ValueError

    # Convert the dm command units to volts.
    max_volts = CONFIG_INI.getint("boston_kilo952", "max_volts")
    dm_command_data *= max_volts
    write_fits(dm_command_data, output_path)

