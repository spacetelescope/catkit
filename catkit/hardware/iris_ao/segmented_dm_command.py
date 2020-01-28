# TODO: Update this for IrisAO

import os
import time
import datetime

from astropy.io import fits
import numpy as np

from catkit.config import CONFIG_INI
from catkit.hardware.iris_ao import iris_ao_parser as iristalk
import catkit.util


m_per_volt_map = None  # for caching the conversion factor, to avoid reading from disk each time


class DmCommand(object):
    def __init__(self, data, flat_map=False):
        """
        Understands the many different formats of dm commands that we have, and returns an object that allows you to
        reliably craft and save commands for the correct DM.

        :param data: numpy array of the following shapes: 34x34, 1x952, 1x2048, 1x4096. Interpreted by default as
                     the desired DM surface height in units of meters, but see parameters as_volts
                     and as_voltage_percentage.
        :param flat_map: If true, add flat map correction to the data before outputting commands

        """

        # calibration_data_package = CONFIG_INI.get("optics_lab", "calibration_data_package")
        # self.calibration_data_path = os.path.join(catkit.util.find_package_location(calibration_data_package),
        #                                           "hardware",
        #                                           "boston") #TODO: Fix me
        self.flat_map = flat_map

        # Load config values once and store as class attributes. (Loop through)
        self.mirror_serial = CONFIG_INI.get('iris_ao', 'mirror_serial')
        self.driver_serial = CONFIG_INI.get('iris_ao', 'driver_serial')
        self.pupil_sim_rings = CONFIG_INI.getint('iris_ao', 'dm_length_actuators') #TODO: What is this?
        self.flat_to_flat = CONFIG_INI.getfloat('iris_ao', 'flat_to_flat')
        self.gap_um = CONFIG_INI.getint('iris_ao', 'gap_um')
        self.flatfile_ini = CONFIG_INI.get('iris_ao', 'flatfile_ini')
        self.c_config_ptt = CONFIG_INI.get('iris_ao', 'c_code_ptt_file')
        self.path_to_dm_exe = CONFIG_INI.get('iris_ao', 'path_to_dm_exe')
        self.full_path_dm_exe = CONFIG_INI.get('iris_ao', 'full_path_dm_exe')

        # Define aperture - full iris or subaperture
        self.number_segments = CONFIG_INI.getint('iris_ao', 'nb_segments')
        self.number_segments_in_pupil = CONFIG_INI.getint('iris_ao', 'pupil_nb_seg')
        # If you are not using the full aperture, must include which segments are used
        if self.number_segments_in_pupil != self.number_segments:
            self.segments_used = CONFIG_INI.get('iris_ao', 'segments_used')

    def get_data(self):
        # Read it!
        return self.data


    def to_dm_command(self):
        # TODO? Do we need this??
        """ Output DM command suitable for sending to the hardware driver

        returns: 1D array, typically 2048 length for HiCAT, in units of percent of max voltage

        """

        dm_command = np.copy(self.data)

        # Apply Flat Map
        if self.flat_map:
            flat_map = self.read_ini(self.filename_flat)
            dm_command.add_map(flat_map)


        return dm_command

    def save_as_fits(self, filepath):
        # Do we need to do this for IrisAO?
        """
        Saves the dm command in the actual format sent to the DM.
        :param filepath: full path with filename.
        :return: the numpy array that was saved to fits.
        """
        dm_command = self.to_dm_command()
        catkit.util.write_fits(dm_command, filepath)
        return dm_command


def load_dm_command(path, flat_map=False, as_volts=False):
    #Need to change units from volts
    """
    Loads a DM command fits file from disk and returns a DmCommand object.
    :param path: Path to the "2d_noflat" dm command.
    :param dm_num: Which DM to create the command for.
    :param flat_map: Apply a flat map in addition to the data.
    :param bias: Apply a constant bias to the command.
    :return: DmCommand object representing the dm command fits file.
    """
    data = fits.getdata(path) # This is significantly more complicated for IrisAO
    return DmCommand(data, flat_map=flat_map, as_volts=as_volts)



def create_flatmap_from_dm_command(dm_command_path, output_path, file_name=None, dm_num=1):
    # TODO: I don't think we need this for IrisAO
    """
    Converts a dm_command_2d.fits to the format used for the flatmap, and outputs a new flatmap fits file.
    :param dm_command_path: Full path to the dm_command_2d.fits file.
    :param output_path: Path to output the new flatmap fits file. Default is hardware/boston/
    :param file_name: Filename for new flatmap fits file. Default is flatmap_<timestamp>.fits
    :return: None
    """
    dm_command_data = fits.getdata(dm_command_path)

    if file_name is None:
        # Create a string representation of the current timestamp.
        time_stamp = time.time()
        date_time_string = datetime.datetime.fromtimestamp(time_stamp).strftime("%Y-%m-%dT%H-%M-%S")
        file_name = "flat_map_volts_{}_{}.fits".format(dm_string, date_time_string)

    if output_path is None:
        raise ValueError

    # Convert the dm command units to volts. #TODO: Figure out unit conversion here
    max_volts = 1.
    dm_command_data *= max_volts
    catkit.util.write_fits(dm_command_data, output_path)


#### FROM JOST
class IrisWavefront(object):
    def __init__(self, wfmap=None, mode='sim'):
            """
            Class that will deal with Iris AO specific wavefront maps in terms of piston, tip and tilt (PTT) per each segment.

            Attributes are "mode" and "wfmap".
            mode saves whether the you have an instance of the simulated Iris AO (sim) like in poppy or an instance of the
            hardware Iris AO. A hardware instance can be centered on the total Iris AO, which is mode="iris", or on the current
            custom pupil, which is mode="custom". All methods can be applied to all three modes, except for "map_to_sim" and
            "map_to_hardware"; albeit some methods will return the instance in a specific mode, once applied.

            sim:    - REMOVE - this is not necessary
                    - saves 19 segments, starting at 0 which is the central segment and going through 1, 2, 3, etc. to 18
                    - characterizes only the custom pupil, ignoring that the physical DM actually has more segments
            full:   - saves 37 segments, numbered by the manufacturer like in its GUI
                    - characterizes a map over the entire physical Iris AO
                    - centered on segment 1
            custom: - saves 37 segments, custom numbering depending on the subaperture that is used
                    - characterizes only the custom pupil, ignoring that the physical DM actually has more segments
                    - centered on the central segment of the custom pupil as defined as first segment in "segments_used"
                      parameter in config

            wfmap saves a tuple of three values for each segment in form of a dictionary. This is an Iris AO style wavefront
            map {seg: (piston, tip, tilt)} that can be loaded directly onto the hardware. The choice fell on this format of
            dictionary because Christopher Moriarty started making a proper context manager for the Iris AO which would be
            independent from the testbed it's used on, and the parsers he wrote use this format.

            Default units are mrad for tip/tilt and um for piston, unless otherwise noted (and there are quite a few methods
            that note different units).

            :param wfmap: str, dict, or np.ndarray. Expect .PTT111, .ini, array (TODO: MAPPING), or dictionary
            :param mode: str # TODO maybe scrap this

            TODO: shift_center: bool, this is only True if mode = custom AND the center segment is not 1
            TODO: Make sure this can be compatible with simulator
            TODO: Where should the ability to make a wf map with POPPY go?
            TODO: determine how to handle "mode"
            """
        self._mode = mode
        self.wfmap = self.read_command(wfmap)
        self._shift_center = False

        # Grab things from CONFIG_INI
        # Load config values once and store as class attributes. (Loop through)
        self.mirror_serial = CONFIG_INI.get('iris_ao', 'mirror_serial')
        self.driver_serial = CONFIG_INI.get('iris_ao', 'driver_serial')
        self.flat_to_flat = CONFIG_INI.getfloat('iris_ao', 'flat_to_flat')
        self.gap_um = CONFIG_INI.getint('iris_ao', 'gap_um')
        self.flatfile_ini = CONFIG_INI.get('iris_ao', 'flatfile_ini')
        self.c_config_ptt = CONFIG_INI.get('iris_ao', 'c_code_ptt_file')
        self.path_to_dm_exe = CONFIG_INI.get('iris_ao', 'path_to_dm_exe')
        self.full_path_dm_exe = CONFIG_INI.get('iris_ao', 'full_path_dm_exe')

        # Define aperture - full iris or subaperture
        self.number_segments = CONFIG_INI.getint('iris_ao', 'nb_segments')
        self.number_segments_in_pupil = CONFIG_INI.getint('iris_ao', 'pupil_nb_seg')
        # If you are not using the full aperture, must include which segments are used
        if self.number_segments_in_pupil != self.number_segments:
            try:
                self.segments_used = CONFIG_INI.get('iris_ao', 'segments_used')
                # TODO: Do assert differently, setter??
                assert len(self.segments_used) == self.number_segments_in_pupil, "Number of segs in pupil must be equal to length of segments used"
            except:
                print("You need to include 'segments_used' in the config.ini file")

        # Get number of rings of segments in pupil
        self.pupil_sim_rings = self.get_num_rings()

        # Set # of segments HERE
        # Change full = 37, custom = whatever you set custom to
        # if self.mode == 'sim':
        #     self.segnum = self.number_segments_in_pupil
        # elif self.mode in ('full', 'custom'):
        #     self.segnum = self.number_segments
        if self.mode == 'custom':
            self.segnum = self.number_segments_in_pupil
            if self.segments_used[0] != 1:
                self._shift_center = True
        elif self.mode == 'full':
            self.segnum = self.number_segments #or just 37


    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, modestring):
        if modestring not in ('full', 'custom'):
            raise ValueError('No valid mode entered.')
        else:
            self._mode = modestring



    def get_num_rings(self):
        """
        Get the number of rings of segments from number_segments_in_pupil

        This is specific for a segmented DM with 37 segments therefore:
          - 37 segments = 3 rings
          - 19 segments = 2 rings
          - 7 segments = 1 ring
          - 1 segment = 0 rings
        """
        seg_nums = [37, 19, 7, 1]
        ring_nums = [3, 2, 1, 0]

        if self.number_segments_in_pupil not in seg_nums:
            raise Exception("Invalid number of segments for number_segments_in_pupil.")

        pupil_sim_rings = [rings for segs, rings in zip(seg_nums, ring_nums) if self.number_segments_in_pupil == segs][0]

        return pupil_sim_rings

    def copy(self, iriswf):
        # TODO: Do we need this??
        """
        Copy an IrisWavefront instance.

        Args:
            iriswf (instance of custom IrisWavefront class): wavefront object you want to copy
        """
        self.wfmap = iriswf.wfmap.copy()
        self.mode = iriswf.mode

    def write_ini(self, path, pup='custom'):
        """
        Write an .ini file from current wfmap.

        If mode of instance is "iris" or "custom" when it gets written to ini, the mode is kept. When writing form a "sim"
        mode, default centering on the ini is "custom", but you can also set that to pup="iris".
        Args:
            path (string): full path to and name of .ini file
            pup (string): what pupil centering you want the written file to have, "iris" or "custom"
        """
        if self._shift_center:
            pass

        if self.mode in ('full', 'custom'):
            printmap = self.wfmap
        elif self.mode == 'sim' and pup == 'custom':
            printmap = shift_wavefront(self.wfmap, mode='sim_to_custom')
        elif self.mode == 'sim' and pup == 'full':
            printmap = shift_wavefront(self.wfmap, mode='sim_to_full')
        else:
            raise Exception('Ths wavefront object or passed pup variable has no valid mode specified.')

        # Write to path
        write_ini_from_dict(printmap, path)
        print('Centering used for saving: {}'.format(pup))

    def map_to_hardware(self, pup='custom'):
        """
        Map a sim wavefront map to a hardware map, centered on either "full" or "custom".

        Mapping from "full" to "custom" and vice versa is currently not supported. To achieve this, first map to sim and
        then map back into the desired hardware mode ("iris" or "custom").
        Args:
            pup: what pupil centering you want to write to, "iris" or "custom"
        """
        if self.mode == 'sim' and pup == 'custom' and self.wfmap:
            self.wfmap = shift_wavefront(self.wfmap, mode='sim_to_custom')
            self.mode = 'custom'
        elif self.mode == 'sim' and pup == 'full' and self.wfmap:
            self.wfmap = shift_wavefront(self.wfmap, mode='sim_to_full')
            self.mode = 'full'
        elif self.mode in ('full', 'custom'):
            raise Exception('This wavefront object is already in hardware mode.\n'
                            'If you want to cast to *other* hardware mode, map to sim first.')

        else:
            raise Exception('This wavefront object has no valid mode specified or no wavefront defined.')

    def map_to_sim(self):
        """
        Map a real wavefront map from center of physical pupil to simulated pupil.
        """
        if self.mode == 'full':
            self.wfmap = shift_wavefront(self.wfmap, mode='full_to_sim')
            self.mode = 'sim'
        elif self.mode == 'custom':
            self.wfmap = shift_wavefront(self.wfmap, mode='custom_to_sim')
            self.mode = 'sim'
        elif self.mode == 'sim':
            raise Exception('This wavefront object is already in software mode.')
        else:
            raise Exception('This wavefront object has no valid mode specified.')

    def add_map(self, added_map):
        # TODO: This only depends on numb of segments, is there a better way to do via segs?
        """
        Add the wfmap of a different wavefront to your wavefront object.
        Args:
            added_map (IrisWavefront): wavefront object to be added to your wavefront
        """
        extra_map = IrisWavefront()
        extra_map.copy(added_map)

        if (self.mode in('full', 'custom') and extra_map.mode in ('full', 'custom')) or (self.mode == extra_map.mode):   # this line can probably be simplified
            print('Own map mode: {}'.format(self.mode))
            print('Added map mode: {}'.format(extra_map.mode))

        elif self.mode == 'sim' and extra_map.mode in('full', 'custom'):
            extra_map.map_to_sim()

        elif extra_map.mode == 'sim':
            extra_map.map_to_hardware(pup=self.mode)

        else:
            raise Exception('Problem with wavefront mode occurred.')

        self.wfmap = add_maps(self.wfmap, extra_map.wfmap)

    def display(self, wf=True, psf=False):
        """
        Display WF and/or PSF

        :param wf: Bool, Display the wavefront
        :param psf: Bool, Display the PSF
        """

        if self.mode == 'sim':
            wf_plot = self.wfmap
        elif self.mode:
            mode='full_to_sim' if self.mode=='full' else 'custom_to_sim'
            wf_plot = shift_wavefront(self.wfmap, mode=mode)
        else:
            raise Exception('Ths wavefront object has no valid mode specified.')

        iris = poppy.dms.HexSegmentedDeformableMirror(name='Iris DM',
                                                      rings=self.pupil_sim_rings),
                                                      flattoflat=self.flat_to_flat) * u.mm,
                                                      gap=self.gap_um * u.micron)
        try:
            iris = deploy_global_wf(iris, wf_plot)
        except AttributeError:
            print('wfmap is none')

        if wf:
            self.display_wf(iris)
        if psf:
            try:
                pixelscale = CONFIG_INI.getfloat("testbed", "pixelscale")
                fov_arcsec = CONFIG_INI.getint("testbed", "fov_arcsec")
                self.display_psf(iris, pixelscale, fov_arcsec)
            except:
                print("Cannot display PSF without instrument 'pixelscale' and 'fov_arcsec'. Please add to config file")

    def display_wf(self, iris):
        """
        Display wfmap as wavefront on Iris AO sim object.
        """
        iris.display(what='opd', title='mode: {}'.format(self.mode))

    def display_psf(self, iris, pixelscale, fov_arcsec):
        """
        Display wfmap on Iris AO sim object as PSF.
        """
        osys = poppy.OpticalSystem()
        osys.add_pupil(iris)
        osys.add_detector(pixelscale=pixelscale, fov_arcsec=fov_arcsec)

        psf = osys.calc_psf(wavelength=638*u.nm)
        print('The PSF generated by Python will be rotated by 90 degrees with respect to a real custom image,'
              'because the camera is in the system on its side.') # TODO: remove comment
        poppy.display_psf(psf, title='mode: {}'.format(self.mode))


def add_maps(map1, map2):
    """
    Add together two wavefront map files for the Iris AO.

    Wavefront information is handled in dictionaries so doing math with them is a bit more complicated. Values with the
    same segment key get added together. Values appearing only in one of the wavefront maps will be included unaltered
    in the final result. This means that the resulting dictionary will either have the same number of or more entries
    than each of the two individual input dictionaries.
    Basic function taken from: https://stackoverflow.com/questions/10461531/merge-and-sum-of-two-dictionaries
    :param map1: dict;
    :param map2:  dict;
    :return: map1 + map2
    """

    # Some fancy dictionary comprehension and set operations.
    # First casting to np.array because math on tuples is hard. Then casting back to tuple because that's what is in
    # the dictionary by default.
    tot_map = {seg: tuple(np.asarray(map1.get(seg, (0.,0.,0.))) + np.asarray(map2.get(seg, (0.,0.,0.)))) for seg in set(map1) | set(map2)}

    return tot_map


def shift_wavefront(map_to_shift, mode):
    #TODO: Cut this down to two options, shift to hardware, shift off harware
    """
    Shift wavefront map between two different reference pupils.

    The different pupils are:
    simcen: 19 segments centered on 0 and numbered from 0-19 from the Iris AO simulation
    iriscen: <= 37 segments centered on 1 and numbered from 1-19 (and until 37) for overall Iris AO pupil
    customcen: >=19 segments centered on first segment number in config and numbered
                specifically for a custom pupil, defining the custom pupil as part of
                the DM

    Mapping options:
        sim_to_custom
        custom_to_sim
        custom_to_full
        full_to_custom
        full_to_sim
        sim_to_full

    Args:
        map_to_shift (dict): wavefront map to be shifted, Iris AO format
        mode (string): which mapping should be performed

    Returns:
        shifted_map (dict): shifted wavefront map, Iris AO format
    """

    # Defining segment numbers for all three pupils in their smallest configuration
    sim_pup = np.array([0, 1, 6, 5, 4, 3, 2, 7, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8]) #TODO: what is this??
    # Flipping the order of counting on sim_pup to make it the same like in custom_pup and full_pup, # TODO: what?
    # but not sure if that is correct. Should there be a left-right and up-down flip in sim_pup instead?
    custom_pup = json.loads(CONFIG_INI.get('iris_ao', 'segments_used'))
    full_pup = np.arange(1, 20) # TODO: Why only 19? Shouldn't this be 37?

    # Shifting map away from physical Iris AO center segment 1 to custom center segment 3.
    if mode == 'full_to_custom':
        # mapping = {new_seg: old_seg}
        mapping = _map_to_new_center(custom_pup, full_pup)

    # Shifting map away from custom center segment 3 to physical Iris AO center segment 1.
    elif mode == 'custom_to_full':
        # mapping = {new_seg: old_seg}
        mapping = _map_to_new_center(full_pup, custom_pup)

    # Shifting map away from simulation center segment 0 to custom center segment 3.
    elif mode == 'sim_to_custom':
        # mapping = {new_seg: old_seg}
        mapping = _map_to_new_center(custom_pup, sim_pup)

        # Shifting map away from custom center segment 3 to simulation center segment 0.
    elif mode == 'custom_to_sim':
        # mapping = {new_seg: old_seg}
        mapping = _map_to_new_center(sim_pup, custom_pup)

        # Shifting map away from physical Iris AO center segment 1 to simulation center segment 0.
    elif mode == 'full_to_sim':
        # mapping = {new_seg: old_seg}
        mapping = _map_to_new_center(sim_pup, full_pup)

    # Shifting map away from simulation center segment 0 to physical Iris AO center segment 1.
    elif mode == 'sim_to_full':
        # mapping = {new_seg: old_seg}
        mapping = _map_to_new_center(full_pup, sim_pup)

    else:
        raise Exception('Mapping not implemented for the mode you entered (maybe a typo?).')

    # Create the new map with the mapping of the input
    shifted_map = {seg: map_to_shift.get(val, (0., 0., 0.)) for seg, val in list(mapping.items())}

    # At a later point, it might be worth including the mapping of segments that get cut out
    # or reappear when going back and forth between full_pup and custom_pup.

    return shifted_map

def _map_to_new_center(new_pupil, old_pupil):
    return dict(zip(new_pupil, old_pupil))


def dict_from_array(wf_array, as_si=True):
    """
    Create an Iris AO wavefront map dictionary in microns and rad from an array in meters and radians.

    segments: 19 -> 19
    mapping: simcen -> simcen
    :param wf_array:
    :return: dict; Iris AO style wavefront map {seg: (piston, tip, tilt)}
    """
    # Create array of number segments we talk to.
    segnum = wf_array.shape[0]
    if segnum != 19:   # we can currently work only with arrays with exactly 19 entries
        raise Exception('Input array must have shape (19, 3).')
    seglist = np.arange(segnum)

    # Put surface information in dict
    wf_dict = {seg: tuple(ptt) for seg, ptt in zip(seglist, wf_array)}

    # Convert from meters and radians to um and mrad.
    if as_si:
        wf_dict = convert_dict_from_si(wf_dict)

    # Round to 3 decimal points after zero.
    rounded = {seg: (np.round(ptt[0], 3), np.round(ptt[1], 3), np.round(ptt[2], 3)) for seg, ptt in list(wf_dict.items())}

    return rounded

def convert_dict_from_si(wf_dict):
    """
    Take a wf dict and convert from SI (meters and radians) to microns and millirads
    """
    converted = {seg: (ptt[0]*(u.m).to(u.um), ptt[1]*(u.rad).to(u.mrad), ptt[2]*(u.rad).to(u.mrad)) for
                 seg, ptt in list(wf_dict.items())}

    return converted

def deploy_global_wf(mirror, wfmap):
    # TODO: How would this be different than any other apply? Just needs to be in correct notebook
    """
    Put a global wavefront on the Iris AO, from an Iris AO dict input wavefront map.

    segments: >=19 -> 19
    mapping: simcen -> simcen
    :param wfmap: dict; wavefront map in Iris AO format {seg: (piston, tip, tilt)}
    :return:
    """
    for seg, vals in list(wfmap.items()):
        if seg in mirror.segmentlist:
            mirror.set_actuator(seg, vals[0]/1e6, -vals[2]/1e3, vals[1]/1e3)   # conversion from um and mrad to m and rad; x and y are flipped, and a minus added to make sim and iris compatible in this application
    return mirror

def load_wf_map(wfmap, flat_map=False, as_si=False):
    """
    Loads a DM command fits file from disk and returns a DmCommand object.
    :param path: Path to the "2d_noflat" dm command.
    :param dm_num: Which DM to create the command for.
    :param flat_map: Apply a flat map in addition to the data.
    :param as_si: Are units in SI or um and mrad? [Do we want this??]
    :return: DmCommand object representing the dm command fits file.
    """
    data, as_si = read_wf_map(wfmap)
    return DmCommand(data, flat_map=flat_map, as_si=as_si)

def read_wf_map(self, command):
    """
    Take in command that can be .PTT111, .ini, array, or dictionary (of length #of segments in pupil)
    Dictionary units must all be the same (microns and millirads?)
    -- TODO - add function for converting units?
    -- TODO - constantly check that the command is the correct length
    """
    try:
        if command.endswith("PTT111"):
            wfmap = iristalk.read_segments(command)
            as_si = False
        elif path.endswith("ini"):
            wfmap = read_ini_to_dict(command)
            as_si = False
        else:
            raise Exception("The command input format is not supported")
    except:
        if isinstance(command, dict):'
            wfmap = command
            as_si = True # TODO: UNITS! ? !
        elif isinstance(command, (list, tuple, np.ndarray)):
            # TODO: Currently dict_from_array expects m and radians
            wfmap = dict_from_array(command)
            as_si = False
        else:
            raise Exception("The command input format is not supported")

    # Check that lengths are correct
    if len(wfmap) != self.number_segments_in_pupil:
        raise Exception("The number of segments in your command MUST equal number of segments in the pupil")

    return wfmap, as_si
