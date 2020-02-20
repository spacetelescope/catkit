"""
Holds the class SegmentedDmCommand that is used to create a dict that will be sent to the
IrisAO hardware as a command.
"""
from configparser import NoOptionError
import json
import os

import astropy.units as u
import matplotlib.pyplot as plt
import numpy as np
import poppy

from catkit.config import CONFIG_INI
from catkit.hardware.iris_ao import util as iris_util


class SegmentedDmCommand(object):
    """
    Handle converting inputs into expected dictionary format to be sent to the Iris AO.
    Does NOT interact with hardware directly.

    :attribute data: dict, Input data, shifted if custom pupil exists in config file
    :attribute flat_map: bool, whether or not to apply the flat map
    :attribute source_pupil_numbering: list, numbering native to data
    :attribute command: dict, Final command with flat if flat_map = True and shift if applicable
    :attribute filename_flat: str, path to flat
    :attribute total_number_segments: int, total number of segments in DM
    :attribute active_segment_list: int, number of active segments in the DM

    Optional if not using full DM:
    :attribute number_segments_in_pupil: int, the number of segments in the pupil.

    """
    def __init__(self, data=None, flat_map=False, config_id='iris_ao'):
        """
        Handle Iris AO specific commands in terms of piston, tip and tilt (PTT) per
        each segment. Creates a Iris AO-style command -{seg: (piston, tip, tilt)} -
        that can be loaded onto the hardware.

        Units are expect to be in um (for piston) and mrad (for tip and tilt)

        :param data: dict, of the form {seg: (piston, tip, tilt)}. If None, will populate
                     with dictionary of zeros for the segments used (This may be used if
                     only adding the flat map)
        :param flat_map: If true, add flat map correction to the data before creating command
        :param source_pupil_numbering: list, if a specific (non-Iris AO native) numbering
                                       exists for this command, pass it in here. This is
                                       particularly necessary for a command created with POPPY
        """
        # Establish variables for pupil shifting
        self._shift_center = False

        # Grab things from CONFIG_INI
        self.filename_flat = CONFIG_INI.get(config_id, 'flat_file_ini') #format is .ini

        # Define aperture - full aperture or subaperture
        # If you are not using the full aperture, must include which segments are used
        try:
            self.segments_in_pupil = json.loads(CONFIG_INI.get(config_id, 'active_segment_list'))
            self.number_segments_in_pupil = CONFIG_INI.getint(config_id, 'active_number_of_segments')
            # if len(data) != len(self.segments_in_pupil):
            #     raise ValueError("The number of segments in your command MUST equal number of segments in the pupil")
            if self.segments_in_pupil[0] != 1:
                self._shift_center = True # Pupil is centered elsewhere, must shift
        except NoOptionError:
            self.segments_in_pupil = iris_util.iris_pupil_numbering()

        if data is None:
            # If no data given, return dictionary of zeros
            data = iris_util.create_zero_dictionary(self.number_segments_in_pupil,
                                                    seglist=self.segments_in_pupil)

        self.data = data
        self.flat_map = flat_map

        if self._shift_center:
            self.data = shift_command(self.data, self.segments_in_pupil)


    def get_data(self):
        """ Grab the current shape to be applied to the DM (does NOT include the flat map)
        """
        return self.data


    def to_command(self):
        """ Output command suitable for sending to the hardware driver
        """
        # Apply Flat Map
        if self.flat_map:
            self.add_map(self.filename_flat, flat=True)

        return self.data


    def add_map(self, segment_values_to_add, flat=False):
        """
        Add a command to the one already loaded.

        Will shift the new command if you are using a shifted pupil. Updates self.data
        with combined commands.

        Will not shift the flat (flat=True) since the flat is segment-specific.

        :param new_command: str or array (.PTT111 or .ini file, or array from POPPY)
        :param flat: bool, only True if the map being added is the flat (so that it is not shifted)
        """
        original_data = self.get_data()
        data_to_add = iris_util.read_segment_values(segment_values_to_add)

        if self._shift_center and not flat:
            data_to_add = shift_command(data_to_add, self.segments_in_pupil,
                                        iris_util.iris_pupil_numbering())

        # Do magic adding only if segment exists in both
        combined_data = {seg: tuple(np.asarray(original_data.get(seg, (0., 0., 0.))) + np.asarray(data_to_add.get(seg, (0., 0., 0.)))) for seg in set(original_data) & set(data_to_add)}

        self.data = combined_data


def shift_command(command_to_shift, to_pupil, from_pupil=None):
    """
    If using a custom pupil, you must shift the numbering from centering in the center
    of the Iris AO, to the center of your pupil.

    This function will shift the pupil from the "from_pupil" (generally centered on the
    full Iris AO) to the "to_pupil" (generally a custom pupil with a custom center)

    Different pupil numbering systems include:
    Full Iris: <= 37 segments centered on 1 and numbered from 1-19 (and until 37)
               for overall Iris AO pupil. This is the default "from_pupil"
               if None is given. This numbering is given by iris_util.iris_pupil_numbering
    Custom: <=19 segments centered on first segment number in "segments_in_pupil" in
            the config file and numbered specifically for a custom pupil, defining
            the custom pupil as part of the DM
    Poppy: POPPY uses a different numbering scheme given by iris_util.poppy_numbering

    :param command_to_shift: dict, wavefront map to be shifted, Iris AO format
    :param to_pupil: list, of segments in the pupil that you are moving to, starting
                     at the center and then continuing counter clockwise
    :param from_pupil: list, segments in the pupil with numbering system you are moving from.
                       If None (default) the Iris AO numbering will be used

    :return: dict, command shifted to expected center
    """
    if from_pupil is None:
        from_pupil = iris_util.iris_pupil_numbering()

    # Match lengths of arrays
    from_pupil, to_pupil = iris_util.match_lengths(from_pupil, to_pupil)

    mapping = iris_util.map_to_new_center(to_pupil, from_pupil)

    # Create the new map with the mapping of the input
    shifted_map = iris_util.remap_dictionary(command_to_shift, mapping)

    return shifted_map


def load_command(segment_values, flat_map=True):
    """
    Loads the segment_values from a file, array, or dictionary and returns a
    SegmentedDmCommand object.

    :param segment_values: str or dict. Can be .PTT111, .ini files,
                           array from POPPY, or dictionary of the same form as the output
    :param flat_map: Apply a flat map in addition to the data.

    :return: SegmentedDmCommand object representing the command dictionary.
    """
    data = iris_util.read_segment_values(segment_values)
    return SegmentedDmCommand(data, flat_map=flat_map)


## POPPY
class PoppySegmentedCommand():
    """
    Create a segement values array (and dictionary) (in POPPY: wavefront error) using
    POPPY for your pupil. This is currently limited to global shapes. The out put is
    either a dictionary of piston, tip, tilt for each segment.

    To use to get command for the Iris AO:

      poppy_obj = PoppySegmentedCommand(global_coefficients)
      command_dict = poppy_obj.to_dictionary()
      iris_command_obj = segmented_dm_command.load_command(command_dict)

    :param global_coefficients: list of global zernike coefficients in the form
                                [piston, tip, tilt, defocus, ...] (Noll convention)
    """
    def __init__(self, global_coefficients):
        # Grab pupil-specific values from config
        self.flat_to_flat = CONFIG_INI.getfloat('iris_ao', 'flat_to_flat_mm')  # [mm]
        self.gap = CONFIG_INI.getint('iris_ao', 'gap_um')  # [um]
        self.num_segs_in_pupil = CONFIG_INI.getint('iris_ao', 'active_number_of_segments')
        self.wavelength = (CONFIG_INI.getint('thorlabs_source_mcls1', 'lambda_nm')*u.nm).to(u.m)

        self.radius = (self.flat_to_flat/2*u.mm).to(u.m)
        self.num_terms = (self.num_segs_in_pupil - 1) * 3

        self.global_coefficients = global_coefficients

        # Create the specific basis for this pupil
        self.basis = self.create_ptt_basis()

        # Create array of coefficients
        self.array_of_coefficients = self.get_array_from_global()


    def create_ptt_basis(self):
        """
        Create the basis needed for getting the per/segment coeffs back

        :return: Poppy Segment_PTT_Basis object for the specified pupil
        """
        pttbasis = poppy.zernike.Segment_PTT_Basis(rings=get_num_rings(self.num_segs_in_pupil),
                                                   flattoflat=self.flat_to_flat,
                                                   gap=self.gap)
        return pttbasis


    def create_wavefront_from_global(self, global_coefficients):
        """
        Given an array of global coefficients, create wavefront

        :param global_coefficients: list of global zernike coefficients in the form
                                    [piston, tip, tilt, defocus, ...] (Noll convention)

        :return: Poppy ZernikeWFE object, the global wavefront described by the input coefficients
        """
        wavefront = poppy.ZernikeWFE(radius=self.radius, coefficients=global_coefficients)
        wavefront_out = wavefront.sample(wavelength=self.wavelength,
                                         grid_size=2*self.radius,
                                         npix=512, what='opd')
        return wavefront_out


    def get_coeffs_from_pttbasis(self, wavefront):
        """
        From a the speficic pttbasis, get back the coeff_array that will be sent as
        a command to the Iris AO

        :param wavefront: Poppy ZernikeWFE object, the global wavefront over the
                          pupil

        :return: np.ndarray, (piston, tip, tilt) values for each segment in the pupil
                 in units of [m] for piston, and [rad] for tip and tilt
        """
        coeff_array = poppy.zernike.opd_expand_segments(wavefront, nterms=self.num_terms,
                                                        basis=self.basis)
        coeff_array = np.reshape(coeff_array, (self.num_segs_in_pupil - 1, 3))

        center_segment = np.array([0.0, 0.0, 0.0]) # Add zeros for center segment
        coeff_array = np.vstack((center_segment, coeff_array))

        return coeff_array


    def get_array_from_global(self):
        """
        From a global coeff array, get back the per-segment coefficient array

        :return: np.ndarray of coefficients for piston, tip, and tilt, for your pupil
        """
        wavefront = self.create_wavefront_from_global(self.global_coefficients)

        coeffs_array = self.get_coeffs_from_pttbasis(wavefront)

        return coeffs_array


    def to_dictionary(self, map_to_iris=True):
        """
        Read in an array produced by POPPY. Each entry in array is a tuple of (piston, tip, tilt)
        values for the segment number that corresponds with the index in the array.

        This function will convert the values in this array from si units to um and mrad, as
        expected by IrisAO .

        :param array: array, of length number of segments in pupil from POPPY with units of:
                      ([m], [rad], [rad])

        :return: dict, command in the form of a dictionary of the form {seg: (piston, tip, tilt)}
                 with units of ([um], [mrad], [mrad])
        """
        # Give seglist so that you guarentee you start at 0
        dictionary = iris_util.create_dict_from_array(self.array_of_coefficients,
                                                      seglist=np.arange(len(self.array_of_coefficients)))
        # Convert from meters and radians (what Poppy outputs) to um and mrad.
        dictionary = iris_util.convert_dict_from_si(dictionary)

        # Round to 3 decimal points after zero.
        command_dict = {seg: (np.round(ptt[0], 3), -1*np.round(ptt[2], 3),
                              np.round(ptt[1], 3)) for seg, ptt in list(dictionary.items())}

        # Re map to Iris AO
        if map_to_iris:
            to_pupil = iris_util.iris_pupil_numbering()[:self.num_segs_in_pupil]
            from_pupil = poppy_numbering()
            command_dict = shift_command(command_dict, to_pupil, from_pupil)

        return command_dict


def poppy_numbering():
    """
    Numbering of the pupil in POPPY. Specifically for a 37 segment Iris AO
    """
    return [0,   # Ring 0
            1, 6, 5, 4, 3, 2,  # Ring 1
            7, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8,  # Ring 2
            19, 36, 35, 34, 33, 32, 31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20]  # Ring 3


def get_num_rings(number_segments_in_pupil):
    """
    Get the number of rings of segments from using the number_segments_in_pupil parameter
    This is specific for a segmented DM with 37 segments therefore:
      - 37 segments = 3 rings
      - 19 segments = 2 rings
      - 7 segments = 1 ring
      - 1 segment = 0 rings

    :param num_segs_in_pupil: int, the number of segments in the pupil.

    :return: num_rings: int, the number of full rings of hexagonal segments in the pupil
    """
    # seg_nums: number of segments in a pupil of the corresponding # of rings
    seg_nums = np.array([37, 19, 7, 1])
    ring_nums = np.array([3, 2, 1, 0])

    if number_segments_in_pupil not in seg_nums:
        raise Exception("Invalid number of segments for number_segments_in_pupil.")

    num_rings = [rings for segs, rings in zip(seg_nums,
                                              ring_nums) if number_segments_in_pupil == segs][0]
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

    :return wavefront, POPPY wavefront
    """
    wavefront = poppy.zernike.opd_from_zernikes(coeff_array, basis=basis)

    return wavefront


def deploy_global_wf(mirror, command_dict):
    """
    Put a global wavefront on the Iris AO, from an Iris AO dict input wavefront map.

    :param mirror: a Poppy HexSegmentedDeformableMirror object
    :param wfmap: dict; wavefront map in Iris AO format {seg: (piston, tip, tilt)}
    :return:
    """
    for seg, vals in command_dict.items():
        if seg in mirror.segmentlist:
            # conversion from um and mrad to m and rad; x and y are flipped, and a minus
            # added to make sim and iris compatible in this application
            mirror.set_actuator(seg, vals[0]*(u.um).to(u.m), -1*vals[2]*(u.mrad).to(u.rad),
                                vals[1]*(u.mrad).to(u.rad))
    return mirror


def display(segment_values, instrument_fov, wavefront=True, psf=True, out_dir=''):
    """
    Display the wavefront or expected psf generated by this wavefront
    """
    if segment_values is None:
        raise ValueError('segment_values cannot be None')

    num_rings = get_num_rings(CONFIG_INI.getint('iris_ao', 'active_number_of_segments'))
    flat_to_flat = CONFIG_INI.getfloat('iris_ao', 'flat_to_flat_mm') * u.mm
    gap = CONFIG_INI.getfloat('iris_ao', 'gap_um') * u.micron
    wavelength = (CONFIG_INI.getint('thorlabs_source_mcls1', 'lambda_nm')*u.nm)

    pixelscale = instrument_fov/512. # arcsec/px, 512 is size of image

    data = iris_util.read_segment_values(segment_values)
    # Shift TO Poppy from the Iris AO
    shifted = shift_command(data, poppy_numbering(), iris_util.iris_pupil_numbering())

    iris = poppy.dms.HexSegmentedDeformableMirror(name='Iris DM',
                                                  rings=num_rings,
                                                  flattoflat=flat_to_flat,
                                                  gap=gap)

    iris = deploy_global_wf(iris, shifted) # takes pupil and dictionary

    if wavefront:
        plt.clf()
        iris.display(what='opd', title='Shape put on the active segments')
        plt.savefig(os.path.join(out_dir, 'shape_on_dm.png'))

    if psf:
        plt.clf()
        osys = poppy.OpticalSystem()
        osys.add_pupil(iris)
        osys.add_detector(pixelscale=pixelscale, fov_arcsec=instrument_fov)

        psf = osys.calc_psf(wavelength=wavelength)
        poppy.display_psf(psf, vmin=10e-8, vmax=10e-2,
                          title='PSF created by the shape put on the active segments')
        #plt.savefig(os.path.join(out_dir, 'simulated_psf.png'))
