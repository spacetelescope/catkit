"""
Utility functions to be used for creating commands for and controlling the IrisAO hardware
"""
from configparser import ConfigParser
import re

import astropy.units as u
import numpy as np
import poppy

from catkit.config import CONFIG_INI



def iris_num_segments():
    """Number of segments in your Iris AO"""
    return CONFIG_INI.getint('iris_ao', 'number_of_segments')


def iris_pupil_numbering():
    """Numbering of the Iris AO pupil """
    return np.arange(iris_num_segments())+1


def map_to_new_center(new_pupil, old_pupil):
    """
    Create a zipped dictionary of the pupil you moving to and the one you are moving
    from
    """
    return dict(zip(new_pupil, old_pupil))


def match_lengths(list_a, list_b):
    """Match the lengths of two arrays
    This assumes they are in the correct order.
    """
    if len(list_a) > len(list_b):
        list_a = list_a[:len(list_b)]
    elif len(list_a) < len(list_b):
        list_b = list_b[:len(list_a)]

    return list_a, list_b

def create_new_dictionary(original_command, mapping_dict):
    """
    Update the PTT dictionary segment numbers based on the mapping dictionary created
    by _map_to_new_center
    """
    return {seg: original_command.get(val, (0., 0., 0.)) for seg, val in list(mapping_dict.items())}


def create_dict_from_array(array, seglist=None):
    """
    Simple take an array of len number of segments, with a tupple of piston, tip, tilt
    and convert to a dictionary

    Seglist is a list of equal length with a single value equal to the segment number
    for the index in the array
    """
    if seglist is None:
        seglist = np.arange(len(array))

    # Put surface information in dict
    command_dict = {seg: tuple(ptt) for seg, ptt in zip(seglist, array)}

    return command_dict


def write_ini(data, path, mirror_serial=None, driver_serial=None):
    """
    Write a new ConfigPTT.ini file containing the command for the Iris AO.

    segments:
    :param data: dict; wavefront map in Iris AO format
    :param path: full path incl. filename to save the configfile to
    :return:
    """
    if not mirror_serial and not driver_serial:
        mirror_serial = CONFIG_INI.get("iris_ao", "mirror_serial")
        driver_serial = CONFIG_INI.get("iris_ao", "driver_serial")

    config = ConfigParser()
    config.optionxform = str   # keep capital letters

    config.add_section('Param')
    config.set('Param', 'nbSegment', str(iris_num_segments()))

    config.add_section('SerialNb')
    config.set('SerialNb', 'mirrorSerial', mirror_serial)
    config.set('SerialNb', 'driverSerial', driver_serial)

    for i in iris_pupil_numbering():
        section = 'Segment{}'.format(i)
        config.add_section(section)
        # If the segment number is present in the dictionary
        if i in list(data.keys()):
            ptt = data.get(i)
            config.set(section, 'z', str(np.round(ptt[0], decimals=3)))
            config.set(section, 'xrad', str(np.round(ptt[1], decimals=3)))
            config.set(section, 'yrad', str(np.round(ptt[2], decimals=3)))
        # If the segment number is not present in dictionary, set it to 0.0
        else:
            config.set(section, 'z', str(0.0))
            config.set(section, 'xrad', str(0.0))
            config.set(section, 'yrad', str(0.0))

    # Save to a file
    with open(path, 'w') as configfile:
        config.write(configfile)


## Read commands
# Functions for reading the .PTT11 file
def __clean_string(line):
    """
    Convenience function - not sure what it is doing
    """
    return re.sub(r"[\n\t\s]*", "", line)


def __convert_to_float(string):
    """Convert a string to a float, if possible
    """
    return float(string) if string else 0.0


def read_global(path):
    """
    This section of a PTT111 file only has one line and it’s called GV.
    This is a uniform ptt command that goes on all the segments. This dm_function
    reads that line.

    Example: [GV: 0, 0, 0]
    """
    with open(path, "r") as irisao_file:
        # Read global line
        raw_line = irisao_file.readline()

        # Clean up the string.
        clean_first_line = __clean_string(raw_line)

        # Check that the type is "GV"
        if clean_first_line[1:3].upper() == "GV":

            # Remove white space, and split the values.
            global_values = clean_first_line.lstrip("[GV:").rstrip("]").split(",")
            global_float = tuple(map(__convert_to_float, global_values))

            # If all zeros, then move on to the zernikes.
            if not all(v == 0 for v in global_float):
                return global_float
            else:
                return None

        else:
            raise Exception("Iris AO file formatting problem, can't process the global line:\n" + raw_line)


def read_zerkines(path):
    """
    The section of a PTT111 file has one number per global Zernike mode, which are called MV.
    read_zernikes() reads those numbers directly, which is only useful if teh value gets passed
    directly back into the IrisAO hardware control, as we can’t read which individual segment
    has what ptt command

    Example: [MV: 1, 0]
    """
    with open(path, "r") as irisao_file:
        raw_line = irisao_file.readline()
        clean_line = __clean_string(raw_line)

        # Skip to the zernike section:
        while clean_line[1:3].upper() != "MV":
            raw_line = irisao_file.readline()
            clean_line = __clean_string(raw_line)

        zernike_commands = []
        while clean_line[1:3].upper() == "MV":

            # Parse line and create of tuples (zernike, value).
            zernike_string_list = clean_line.lstrip("[MV:").rstrip("]").split(",")
            zernike_type = int(zernike_string_list[0])
            zernike_value = __convert_to_float(zernike_string_list[1])

            if zernike_value != 0:
                zernike_commands.append((zernike_type, zernike_value))

            raw_line = irisao_file.readline()
            clean_line = __clean_string(raw_line)

        if zernike_commands:
            return zernike_commands
        else:
            return None


def read_segments(path):
    """
    Read the zerinke values for P T T for each segment
    In this section of a PTT111 file, each segment gets a ptt command (ZV), which
    is read by this function. In this case, the lines are populated with the segment
    number, piston, tip, tilt.

    Example : [ZV: 1, 0, 0, 0]
    """
    with open(path, "r") as irisao_file:
        raw_line = irisao_file.readline()
        clean_line = __clean_string(raw_line)

        # Skip to the segment section:
        while clean_line[1:3].upper() != "ZV":
            raw_line = irisao_file.readline()
            clean_line = __clean_string(raw_line)

        segment_commands = {}
        while clean_line[1:3].upper() == "ZV":

            # Parse into dictionary {segment: (piston, tip, tilt)}.
            segment_string_list = clean_line.lstrip("[ZV:").rstrip("]").split(",")
            segment_num = int(segment_string_list[0])
            segment_tuple = __convert_to_float(segment_string_list[1]), \
                            __convert_to_float(segment_string_list[2]), \
                            __convert_to_float(segment_string_list[3])

            if any(segment_tuple):
                segment_commands[segment_num] = segment_tuple

            raw_line = irisao_file.readline()
            clean_line = __clean_string(raw_line)

        if segment_commands:
            # Prepare command for segments.
            return segment_commands
        else:
            return None


def read_ptt111(path):
    """
    Read the entirety of a PTT111 file
    """

    # Read the global portion of the file, and return the command if it's present.
    global_command = read_global(path)
    if global_command is not None:

        # Create a dictionary and apply global commands to all segments.
        command_dict = {}
        for i in range(iris_num_segments()):
            command_dict[i + 1] = global_command
        return command_dict

    # Read in the zernike aka "modal" lines and do error checking.
    zernike_commands = read_zerkines(path)
    if zernike_commands is not None:
        return zernike_commands

    # Read in the segment commands.
    segment_commands = read_segments(path)
    if segment_commands is not None:
        return segment_commands

    # No command found in file.
    return None


def read_ini(path):
    """
    Read the Iris AO segment PTT parameters from an .ini file into Iris AO style
    dictionary {segnum: (piston, tip, tilt)}.

    This expects 37 segments with centering such that it is in the center of the IrisAO

    :param path: path and filename of ini file to be read
    :return command_dict: dict; {segnum: (piston, tip, tilt)}
    """
    config = ConfigParser()
    config.optionxform = str   # keep capital letters
    config.read(path)

    command_dict = {}
    for i in range(iris_num_segments()):
        section = 'Segment{}'.format(i+1)
        piston = float(config.get(section, 'z'))
        tip = float(config.get(section, 'xrad'))
        tilt = float(config.get(section, 'yrad'))
        command_dict[i+1] = (piston, tip, tilt)

    return command_dict


def read_poppy_array(array):
    """
    Read in an array produced by POPPY for the number of segments in your pupil.
    Each entry in array is a tuple of (piston, tip, tilt) values for that segment.
    Segment numbering is TO BE DETERMINED

    Will convert the values in this array from si units to um and mrad, as expected
    by IrisAO.

    :param array: array, of length number of segments in pupil. Units of: ([m], [rad], [rad])
    :return: dict; of the format {seg: (piston, tip, tilt)}
    """
    #The output from poppy
    #doesn't matter length  - that is figured out in segmented_dm_command
    #TODO: Check with Iva, which array should segnum be for outputs from Poppy

    command_dict = create_dict_from_array(array, seglist=None)

    # Convert from meters and radians (what Poppy outputs) to um and mrad.
    command_dict = convert_dict_from_si(command_dict)

    # Round to 3 decimal points after zero.
    rounded = {seg: (np.round(ptt[0], 3), np.round(ptt[1], 3),
                     np.round(ptt[2], 3)) for seg, ptt in list(command_dict.items())}

    return rounded


def convert_dict_from_si(command_dict):
    """
    Take a wf dict and convert from SI (meters and radians) to microns and millirads
    """
    converted = {seg: (ptt[0]*(u.m).to(u.um), ptt[1]*(u.rad).to(u.mrad), ptt[2]*(u.rad).to(u.mrad)) for
                 seg, ptt in list(command_dict.items())}

    return converted


def read_command(command):
    """
    Each of the following formats can be tread in. read_command takes in
    any of these three formats and converts it to a dictionary of the form:
            {seg:(piston, tip, tilt)}
    With units of : ([um], [mrad], [mrad])

    - .PTT111 file: File format of the command coming out of the IrisAO GUI
    - .ini file: File format of command that gets sent to the IrisAO controls
    - array: Format that POPPY outputs if generating command in POPPY

    :param command: str, list, np.ndarray. Can be .PTT111, .ini files or array
    :return command_dict: dict, command in the form of a dictionary
    """
    numbering = None
    try:
        if command.endswith("PTT111"):
            command_dict = read_segments(command)
        elif command.endswith("ini"):
            command_dict = read_ini(command)
        else:
            raise Exception("The command input format is not supported")
    except AttributeError:
        if isinstance(command, (list, tuple, np.ndarray)):
            command_dict = read_poppy_array(command)
            numbering = poppy_numbering()
        elif command is None:
            command_dict = command
        else:
            raise Exception("The command input format is not supported")

    return command_dict, numbering


## POPPY
def poppy_numbering():
    """
    Numbering of the pupil in POPPY. Specifically for a 37 segment Iris AO"""
    return [0,   # Ring 0
            1, 6, 5, 4, 3, 2,  # Ring 1
            7, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8,  # Ring 2
            19, 36, 35, 34, 33, 32, 31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20]  # Ring 3

class PoppySegmentedCommand(object):
    """
    Create an array command (in POPPY: wavefront error) using POPPY for your pupil.
    This is limited to global shapes. This is an array of piston, tip, tilt for each
    segments.

    To use to get command for the Iris AO:

      poppy_obj = PoppySegmentedCommand(global_coefficients)
      coeffs_array = poppy_obj.to_array()
      iris_command_obj = segmented_dm_command.load_command(coeffs_array)
    """
    def __init__(self, global_coefficients):
        # Grab pupil-specific values from config
        self.flat_to_flat = CONFIG_INI.getfloat('iris_ao', 'flat_to_flat_mm')  # [mm]
        self.gap = CONFIG_INI.getint('iris_ao', 'gap_um')  # [um]
        self.num_segs_in_pupil = CONFIG_INI.getint('iris_ao', 'number_of_segments_pupil')
        self.wavelength = (CONFIG_INI.getint('thorlabs_source_mcls1', 'lambda_nm')*u.nm).to(u.m)

        self.radius = (self.flat_to_flat/2*u.mm).to(u.m)
        self.num_terms = (self.num_segs_in_pupil - 1) * 3

        self.global_coefficients = global_coefficients

        # Create the specific basis for this pupil
        self.basis = self.create_ptt_basis()


    def create_ptt_basis(self):
        """
        Create the basis needed for getting the per/segment coeffs back
        """
        pttbasis = poppy.zernike.Segment_PTT_Basis(rings=get_num_rings(self.num_segs_in_pupil),
                                                   flattoflat=self.flat_to_flat,
                                                   gap=self.gap)
        return pttbasis


    def create_wavefront_from_global(self, global_coeff):
        """
        Given an array of global coefficients, create wavefront

        :param global_coeff
        """
        wavefront = poppy.ZernikeWFE(radius=self.radius, coefficients=global_coeff)
        # Sample the WFE onto an actual array
        wavefront_out = wavefront.sample(wavelength=self.wavelength,
                                         grid_size=2*self.radius,
                                         npix=512, what='opd')
        return wavefront_out


    def get_coeffs_from_pttbasis(self, wavefront):
        """
        From a the speficic pttbasis, get back the coeff_array that will be sent as
        a command to the Iris AO
        """
        coeff_array = poppy.zernike.opd_expand_segments(wavefront, nterms=self.num_terms,
                                                        basis=self.basis)
        coeff_array = np.reshape(coeff_array, (self.num_segs_in_pupil - 1, 3))

        center_segment = np.array([0.0, 0.0, 0.0]) # Add zeros for center segment
        coeff_array = np.vstack((center_segment, coeff_array))

        return coeff_array


    def to_array(self):
        """
        From a global coeff array, get back the per-segment coefficient array

        :param global_coeff: Array of global coefficents

        :returns coeffs_array: Array of coefficients for Piston, Tip, and Tilt, for your pupil
        """
        wavefront = self.create_wavefront_from_global(self.global_coefficients)

        coeffs_array = self.get_coeffs_from_pttbasis(wavefront)

        self.array_of_coefficients = coeffs_array

        return coeffs_array


def get_num_rings(num_segs_in_pupil):
    """
    Get the number of rings of segments from number_segments_in_pupil
    This is specific for a segmented DM with 37 segments therefore:
      - 37 segments = 3 rings
      - 19 segments = 2 rings
      - 7 segments = 1 ring
      - 1 segment = 0 rings
    """
    # seg_nums: number of segments in a pupil of the corresponding # of rings
    seg_nums = np.array([37, 19, 7, 1])
    ring_nums = np.array([3, 2, 1, 0])

    if num_segs_in_pupil not in seg_nums:
        raise Exception("Invalid number of segments for number_segments_in_pupil.")

    num_rings = [rings for segs, rings in zip(seg_nums,
                                              ring_nums) if num_segs_in_pupil == segs][0]
    return num_rings


def get_wavefront_from_coeffs(basis, coeff_array):
    """
    Get the wavefront from the coefficients created by the basis given. This gives
    the per-segment wavefront based on the global coefficients given and the basis
    created.

    :params basis: POPPY Segment_PTT_Basis object, basis created that represents
                   pupil
    :params coeff_array: array, per-segment array of piston, tip, tilt values for
                         the pupil described by basis

    :returns wavefront, POPPY wavefront
    """
    wavefront = poppy.zernike.opd_from_zernikes(coeff_array, basis=basis)

    return wavefront
