import importlib
import os
import logging
import logging.handlers
from catkit.catkit_types import MetaDataEntry

import numpy as np
from astropy.io import fits

from catkit.catkit_types import quantity


def find_package_location(package='catkit'):
    return importlib.util.find_spec(package).submodule_search_locations[0]


def find_repo_location(package='cakit'):
    return os.path.abspath(os.path.join(find_package_location(package), os.pardir))


def get_dm_mask():
    mask_path = os.path.join(find_package_location("catkit"), "hardware", "boston", "kiloCdm_2Dmask.fits")
    mask = fits.open(mask_path)[0].data
    return mask


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


def save_images(images, meta_data, path, base_filename, raw_skip=0):
    """
    :param raw_skip: Skips x writes for every one taken.
    :param path: Path of the directory to save fits file to.
    :param base_filename: Name for file.
    :return: None
    """

    if not isinstance(images, (list, tuple)):
        images = [images]

    if not images:
        return

    # Check that path and filename are specified.
    if path is None or base_filename is None:
        raise Exception("You need to specify path and filename.")

    log = logging.getLogger()
    filename = base_filename
    # Check for fits extension.
    if not base_filename.endswith((".fit", ".fits")):
        filename += ".fits"

    # Split the filename once here, code below may append _frame=xxx to basename.
    file_root, file_ext = os.path.splitext(filename)

    # Create directory if it doesn't exist.
    if not os.path.exists(path):
        os.makedirs(path)

    num_exposures = len(images)

    skip_counter = 0
    for i, img in enumerate(images):

        # For multiple exposures append frame number to end of base file name.
        if num_exposures > 1:
            filename = file_root + "_frame" + str(i + 1) + file_ext
        full_path = os.path.join(path, filename)

        # Skip writing the fits files per the raw_skip value, and keep img data in memory.
        if raw_skip != 0:
            if skip_counter == (raw_skip + 1):
                skip_counter = 0
            if skip_counter == 0:
                # Write fits.
                skip_counter += 1
            elif skip_counter > 0:
                # Skip fits.
                skip_counter += 1
                continue

        # Create a PrimaryHDU object to encapsulate the data.
        hdu = fits.PrimaryHDU(img)

        # Add headers.
        hdu.header["FRAME"] = i + 1
        hdu.header["FILENAME"] = filename

        # Add file Path to meta/header for introspection.
        hdu.header["PATH"] = full_path
        # The meta data could be an astropy.io.fits.Header or a list of MetaDataEntrys.
        if isinstance(meta_data, fits.Header):
            meta_data["PATH"] = full_path
        elif isinstance(meta_data, list):
            meta_data.append((MetaDataEntry("PATH", "PATH", full_path, "File path on disk")))

        if meta_data:
            # Add testbed state metadata.
            for entry in meta_data:
                if len(entry.name_8chars) > 8:
                    log.warning("Fits Header Keyword: " + entry.name_8chars +
                                " is greater than 8 characters and will be truncated.")
                if len(entry.comment) > 47:
                    log.warning("Fits Header comment for " + entry.name_8chars +
                                " is greater than 47 characters and will be truncated.")
                value = entry.value.magnitude if isinstance(entry.value, quantity) else entry.value
                hdu.header[entry.name_8chars[:8]] = (value, entry.comment)

        hdu.writeto(full_path, overwrite=True)
        log.info(f"'{full_path}' written to disk.")
