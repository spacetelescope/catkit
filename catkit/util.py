import importlib
import os
import logging
import logging.handlers
import psutil
import signal
import time
from catkit.catkit_types import MetaDataEntry

import numpy as np
from astropy.io import fits

from catkit.catkit_types import quantity


simulation = False


def sleep(seconds):
    global simulation
    if not simulation:
        time.sleep(seconds)


def find_package_location(package='catkit'):
    return importlib.util.find_spec(package).submodule_search_locations[0]


def find_repo_location(package='catkit'):
    return os.path.abspath(os.path.join(find_package_location(package), os.pardir))


def get_dm_mask():
    if not hasattr(get_dm_mask, 'mask'):
        mask_path = os.path.join(find_package_location("catkit"), "hardware", "boston", "kiloCdm_2Dmask.fits")
        get_dm_mask.mask = fits.getdata(mask_path)

    return get_dm_mask.mask


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
    :param raw_skip: Skips x writes for every one taken. np.isinf(raw_skip) will skip all and save nothing.
    :param path: Path of the directory to save fits file to.
    :param base_filename: Name for file.
    :return: None
    """

    if not isinstance(images, (list, tuple)):
        images = [images]

    if not images:
        return

    # Allow raw_skip="infinity" where float("infinity") -> math.inf
    if isinstance(raw_skip, str):
        raw_skip = float(raw_skip)
    if np.isinf(raw_skip):
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

        # Add header info.
        hdu.header["FRAME"] = i + 1
        hdu.header["FILENAME"] = filename
        hdu.header["PATH"] = full_path  # Add file Path for introspection.

        # The meta data could be an astropy.io.fits.Header or a list of MetaDataEntrys.
        if isinstance(meta_data, fits.Header):
            # Add this info to meta_data so that it persist beyond this call.
            meta_data["PATH"] = full_path
            meta_data["FRAME"] = i + 1
            meta_data["FILENAME"] = filename
            hdu.header.update(meta_data)
        elif isinstance(meta_data, list):
            meta_data.append((MetaDataEntry("PATH", "PATH", full_path, "File path on disk")))
            meta_data.append((MetaDataEntry("FRAME", "FRAME", i + 1, "Frame")))
            meta_data.append((MetaDataEntry("FILENAME", "FILENAME", full_path, "Filename")))
            for entry in meta_data:
                if not isinstance(entry, MetaDataEntry):
                    raise TypeError(f"Expected '{MetaDataEntry.__qualname__}' but got '{type(MetaDataEntry)}'")
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


def str2bool(buffer):
    if buffer.lower() == "true":
        return True
    elif buffer.lower() == "false":
        return False
    else:
        raise ValueError(f"Expected case insensitive bool but got '{buffer}'")


def soft_kill(process):
    """
    Sends a "ctrl-c"-like event to a process to allow context managers to close gracefully. The function will
    wait until the process closes.  Uses a console ctrl event for windows, and signal.SIGINT for linux/mac.
    :param process: A multiprocessing.Process object.
    """

    # The process may not have even started...
    if not process or process.pid is None or not process.is_alive():
        return

    signum = signal.SIGINT

    log = logging.getLogger()
    if os.name == "nt":
        try:
            log.info("Sending ctrl-c event...")
            raise_signal(signum)
            while process.is_alive():
                log.info("Child process is still alive...")
                sleep(1)
            log.info("Child process softly killed.")
        except KeyboardInterrupt:
            log.exception("Main process: caught ctrl-c")
    else:
        try:
            log.info("Sending ctrl-c event...")
            raise_signal(signum)
            while process.is_alive():
                log.info("Child process is still alive...")
                sleep(1)
            log.info("Child process softly killed.")
        except KeyboardInterrupt:
            log.exception("Main process: caught ctrl-c")


def raise_signal(signum):
    """ Send SIGINT to current process. """
    # NOTE: This should be used instead of `_thread.interrupt_main()` as that doesn't interrupt sleep() and wait().

    if signum is not signal.SIGINT:
        raise NotImplementedError()
    # TODO: With Python 3.8 signal.raise_signal(signal.SIGINT) can be used instead.
    if os.name == "nt":
        # TODO: `os.kill()` is documented as available on windows so the following shouldn't be needed.
        import win32api
        import win32con
        win32api.GenerateConsoleCtrlEvent(win32con.CTRL_C_EVENT, 0)
    else:
        os.kill(os.getpid(), signal.SIGINT)


def bit_check(data, bit):
    mask = (data >> (bit - 1))
    return mask & 1


def bit_set(data, bit, value=True):
    """ Note: This is NOT in place. """
    value = bool(value)
    mask = (1 << (bit - 1))
    if value:
        # Set high.
        return data | mask
    else:
        # Set low.
        return data & ~mask


def poll_status(break_states, func, timeout=60, poll_interval=0):
    """ Used to poll status whilst motor is in motion.
    This polls the device by calling `func` at intervals of self.QUERY_DELAY until `func() is in break_states`.
    :param break_states: iterable of states - Stop polling when func() returns a value matching that in break_states.
    :param func: callable - The function called to query the device status.
    :param timeout: int, float (optional) - Raise TimeoutError if break_states are not met within timeout seconds.
    :returns: Returns the last value returned from func().
    """

    timeout_ns = timeout * 1e9  # Convert s -> ns.

    status = None
    counter = 0
    while counter < timeout_ns:
        t0 = time.perf_counter_ns()
        status = func()

        if poll_interval:
            time.sleep(poll_interval)

        t = time.perf_counter_ns() - t0

        if status in break_states:
            break

        # NOTE: There's no need to sleep between iterations as there is already a query delay effectively doing the
        # same thing.
        if timeout_ns is not None and timeout_ns > 0:
            counter += t

    if counter >= timeout_ns:
        raise TimeoutError(f"Motor failed to complete operation within {timeout}s, took {counter/1e9}s")

    return status


def to_ascii_hex_pair(x):
    y = f"{x:X}"
    if len(y) % 2 != 0:
        # pad leading 0
        y = "0" + y
    return y


def lrc(msg):
    lrc = 0
    for byte in msg.encode("ascii"):
        lrc ^= byte
    return lrc


def is_process_alive(process_id):
    """ Query processes for `process_id`

    :param process_id: str, int - Process name or PID.

    :return: bool
    """
    for p in psutil.process_iter():
        try:
            if process_id in (p.name(), p.pid):
                return True
        except psutil.NoSuchProcess:
            # We don't care whether zombie processes (never present on Windows).
            continue
    return False
