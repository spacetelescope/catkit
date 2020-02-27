import os
import time
import datetime

from astropy.io import fits
import numpy as np

from catkit.config import CONFIG_INI
import catkit.util


m_per_volt_map1 = None  # for caching the conversion factor, to avoid reading from disk each time
m_per_volt_map2 = None  # for caching the conversion factor, to avoid reading from disk each time


class DmCommand(object):
    def __init__(self, data, dm_num, flat_map=False, bias=False, as_voltage_percentage=False,
                 as_volts=False, sin_specification=None):
        """
        Understands the many different formats of dm commands that we have, and returns an object that allows you to
        reliably craft and save commands for the correct DM.

        :param data: numpy array of the following shapes: 34x34, 1x952, 1x2048, 1x4096. Interpreted by default as
                     the desired DM surface height in units of meters, but see parameters as_volts
                     and as_voltage_percentage.
        :param dm_num: Valid values are 0, 1, 2.  Default is 0, which will automatically identify which dm to use.
                     You can specify 1 or 2 to ensure a certain DM is used, regardless of how the input data is padded.
        :param flat_map: If true, add flat map correction to the data before outputting commands
        :param bias: If true, add bias to the data before outputting commands
        :param as_voltage_percentage: Interpret the data as a voltage percentage instead of meters; Deprecated.
        :param as_volts: If true, interpret the data as volts instead of meters
        :param sin_specification: Add this sine to the data

        """

        calibration_data_package = CONFIG_INI.get("optics_lab", "calibration_data_package")
        self.calibration_data_path = os.path.join(catkit.util.find_package_location(calibration_data_package),
                                                  "hardware",
                                                  "boston")
        self.dm_num = dm_num
        self.flat_map = flat_map
        self.bias = bias
        self.as_voltage_percentage = as_voltage_percentage
        self.as_volts = as_volts

        if sin_specification is None:
            self.sin_specification = []
        else:
            self.sin_specification = sin_specification if isinstance(sin_specification, list) else [sin_specification]

        # Load config values once and store as class attributes.
        self.total_actuators = CONFIG_INI.getint('boston_kilo952', 'number_of_actuators')
        self.command_length = CONFIG_INI.getint('boston_kilo952', 'command_length')
        self.pupil_length = CONFIG_INI.getint('boston_kilo952', 'dm_length_actuators')
        self.max_volts = CONFIG_INI.getint('boston_kilo952', 'max_volts')
        self.bias_volts_dm1 = CONFIG_INI.getint('boston_kilo952', 'bias_volts_dm1')
        self.bias_volts_dm2 = CONFIG_INI.getint('boston_kilo952', 'bias_volts_dm2')

        # Error handling for dm_num.
        if not (dm_num == 1 or dm_num == 2):
            raise ValueError("The parameter dm_num must be 1 or 2.")

        if flat_map and bias:
            raise ValueError("You can only apply flat_map or bias, not both.")

        # Transform data to be a 2D array (ex: 34 x 34 for boston_kilo952).
        # Already 2D, store as-is.
        if data.shape == (self.pupil_length, self.pupil_length):
            self.data = data

        # 1D and no padding, convert to 2D using mask index.
        elif data.ndim == 1 and data.size == self.total_actuators:
            self.data = convert_dm_command_to_image(data)

        # Support for old DM Commands created for Labview of size 4096.
        elif data.ndim == 1 and data.size == 4096:
            self.data = convert_dm_command_to_image(data[0:952])

        else:
            raise ValueError("Data needs to be a 1D array of size " + str(self.total_actuators) + " or " +
                             "a 2D array of size " + str(self.pupil_length) + "," + str(self.pupil_length))

    def get_data(self):
        return self.data

    def to_dm_command(self):
        """ Output DM command suitable for sending to the hardware driver

        returns: 1D array, typically 2048 length for HiCAT, in units of percent of max voltage

        """

        dm_command = np.copy(self.data)

        # Convert legacy "voltage percentage" data to straight volts.
        if self.as_voltage_percentage:
            self.data *= 2

        # Otherwise convert meters to volts and apply appropriate corrections and bias.
        else:
            if not self.as_volts:
                dm_command = convert_m_to_volts((self.data))

            # Apply bias.
            if self.bias:
                dm_command += self.bias_volts_dm1 if self.dm_num == 1 else self.bias_volts_dm2

            # OR apply Flat Map (which is itself biased).
            elif self.flat_map:
                if self.dm_num == 1:
                    flat_map_file_name = CONFIG_INI.get("boston_kilo952", "flat_map_dm1")
                    flat_map_volts = fits.open(os.path.join(self.calibration_data_path, flat_map_file_name))
                    dm_command += flat_map_volts[0].data
                else:
                    flat_map_file_name = CONFIG_INI.get("boston_kilo952", "flat_map_dm2")
                    flat_map_volts = fits.open(os.path.join(self.calibration_data_path, flat_map_file_name))
                    dm_command += flat_map_volts[0].data

            # Convert between 0-1.
            dm_command /= self.max_volts

        # Flatten the command using the mask index.
        dm_command = convert_dm_image_to_command(dm_command)

        if self.dm_num == 1:
            dm_command = np.append(dm_command, np.zeros(self.command_length - dm_command.size))
        else:
            zero_buffer = np.zeros(int(self.command_length / 2))
            dm_command = np.append(zero_buffer, dm_command)
            dm_command = np.append(dm_command, np.zeros(self.command_length - dm_command.size))

        return dm_command

    def save_as_fits(self, filepath):
        """
        Saves the dm command in the actual format sent to the DM.
        :param filepath: full path with filename.
        :return: the numpy array that was saved to fits.
        """
        dm_command = self.to_dm_command()
        catkit.util.write_fits(dm_command, filepath)
        return dm_command

    def export_fits(self, path, folder_name="dm_command"):
        """ Export DM commands to disk.

        Saves the dm command in three different formats:
        - 1D representation of the command (2048 x 1; DM1 commands in 0:952, DM2 in 1024:1976)
        - 2D representation of the command with no padding (34 x 34).
        - 2D command with the flat/bias removed (34 x 34).

        :param path: Path to a directory to create a folder named "dm_command" and save the 3 files.
        :param folder_name: Optional parameter to specify a folder to store the fits file to.

        Separate files are written for each DM, named as 'dm1_*' and 'dm2_*'. The actual full command sent to the
        drive electronics is the summation of the two 1D commands for DM1 and DM2.

        """

        # Add dm_command folder and join the path back up.
        dir_path = os.path.join(path, folder_name)

        # Save 1D representation of the command with no padding (1 x 952).
        dm_command_1d = self.to_dm_command()[0:self.total_actuators] if self.dm_num == 1 \
            else self.to_dm_command()[1024:1024 + self.total_actuators]

        catkit.util.write_fits(self.to_dm_command(), os.path.join(dir_path, "dm{}_command_1d".format(self.dm_num)))

        # Save 2D representation of the command with no padding (34 x 34).
        catkit.util.write_fits(convert_dm_command_to_image(dm_command_1d),
                              os.path.join(dir_path, "dm{}_command_2d".format(self.dm_num)))

        # Save raw data as input to the simulator.
        catkit.util.write_fits(self.data, os.path.join(dir_path, "dm{}_command_2d_noflat".format(self.dm_num)))


def load_dm_command(path, dm_num=1, flat_map=False, bias=False, as_volts=False):
    """
    Loads a DM command fits file from disk and returns a DmCommand object.
    :param path: Path to the "2d_noflat" dm command.
    :param dm_num: Which DM to create the command for.
    :param flat_map: Apply a flat map in addition to the data.
    :param bias: Apply a constant bias to the command.
    :return: DmCommand object representing the dm command fits file.
    """
    data = fits.getdata(path)
    return DmCommand(data, dm_num, flat_map=flat_map, bias=bias, as_volts=as_volts)


def get_flat_map_volts(dm_num):
    calibration_data_package = CONFIG_INI.get("optics_lab", "calibration_data_package")
    calibration_data_path = os.path.join(catkit.util.find_package_location(calibration_data_package),
                                         "hardware",
                                         "boston")
    if dm_num == 1:
        flat_map_file_name = CONFIG_INI.get("boston_kilo952", "flat_map_dm1")
        flat_map_volts = fits.open(os.path.join(calibration_data_path, flat_map_file_name))
        return flat_map_volts[0].data
    else:
        flat_map_file_name = CONFIG_INI.get("boston_kilo952", "flat_map_dm2")
        flat_map_volts = fits.open(os.path.join(calibration_data_path, flat_map_file_name))
        return flat_map_volts[0].data


def get_m_per_volt_map(dn_num):
    calibration_data_package = CONFIG_INI.get("optics_lab", "calibration_data_package")
    calibration_data_path = os.path.join(catkit.util.find_package_location(calibration_data_package),
                                         "hardware",
                                         "boston")
    if dm_num == 1:
        global m_per_volt_map1
        if m_per_volt_map1 is None:
            m_per_volt_map1 = fits.getdata(os.path.join(calibration_data_path,
                                               CONFIG_INI.get("boston_kilo952", "gain_map_dm1")))
        m_per_volt_map = m_per_volt_map1

    elif dm_num == 2:
        global m_per_volt_map2
        if m_per_volt_map2 is None:
            m_per_volt_map2 = fits.getdata(os.path.join(calibration_data_path,
                                               CONFIG_INI.get("boston_kilo952", "gain_map_dm2")))
        m_per_volt_map = m_per_volt_map2

    return m_per_volt_map


def convert_volts_to_m(data, meter_to_volt_map=None):
    """
    Convert volts to meters for DM commands.
    Inverse of convert_m_to_volts

    :param data: array-like
        DM commands in volts
    :param meter_to_volt_map: array-like
        The calibration array used to map/convert volts to DM surface height in meters.

    :return: DM commands in meters
    """

    if meter_to_volt_map is None:
        meter_to_volt_map = get_m_per_volt_map()
    return data * meter_to_volt_map


def convert_m_to_volts(data, meter_to_volt_map=None):
    """
    Convert meters to volts for DM commands.
    Inverse of convert_volts_to_m

    :param data:  DM commands in meters

    :return: DM commands in volts
    """

    if meter_to_volt_map is None:
        meter_to_volt_map = get_m_per_volt_map()
    return catkit.util.safe_divide(data, meter_to_volt_map)


def convert_dm_command_to_image(dm_command):
    # Flatten the mask using index952
    mask = catkit.util.get_dm_mask()
    index952 = np.flatnonzero(mask)

    number_of_actuators_per_dimension = CONFIG_INI.getint('boston_kilo952', 'dm_length_actuators')
    number_of_actuators = CONFIG_INI.getint("boston_kilo952", "number_of_actuators")
    image = np.zeros((number_of_actuators_per_dimension, number_of_actuators_per_dimension))
    image[np.unravel_index(index952, image.shape)] = dm_command[:number_of_actuators]

    return image


def convert_dm_image_to_command(dm_image, path_to_save=None):
    # Flatten the gain_map using index952
    mask = catkit.util.get_dm_mask()
    index952 = np.flatnonzero(mask)

    # Parse using index952.
    image_1d = np.ndarray.flatten(dm_image)
    dm_command = image_1d[index952]

    # Write new image as fits file
    if path_to_save is not None:
        catkit.util.write_fits(dm_command, path_to_save)
    return dm_command


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
    catkit.util.write_fits(dm_command_data, output_path)
