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
    :attribute apply_flat_map: bool, whether or not to apply the flat map
    :attribute source_pupil_numbering: list, numbering native to data
    :attribute command: dict, Final command with flat if apply_flat_map = True and shift if applicable
    :attribute filename_flat: str, path to flat
    :attribute total_number_segments: int, total number of segments in DM
    :attribute active_segment_list: int, number of active segments in the DM

    Optional if not using full DM:
    :attribute number_segments_in_pupil: int, the number of segments in the pupil.

    """
    def __init__(self, apply_flat_map=False, config_id='iris_ao'):
        """
        Handle Iris AO specific commands in terms of piston, tip and tilt (PTT) per
        each segment. Creates a Iris AO-style command -{seg: (piston, tip, tilt)} -
        that can be loaded onto the hardware.

        Units are expect to be in um (for piston) and mrad (for tip and tilt)

        :param apply_flat_map: If true, add flat map correction to the data before creating command
        :param convert_to_native_mapping: bool, if True, convert the input command to the
                                          Iris native numbering. If False, the command is
                                          assumed to be in the Iris frame already.
        """
        # Establish variables for pupil shifting
        self._shift_center = False

        # Grab things from CONFIG_INI
        self.filename_flat = CONFIG_INI.get(config_id, 'flat_file_ini') #format is .ini

        try:
            self.segments_in_pupil = json.loads(CONFIG_INI.get(config_id, 'active_segment_list'))
            self.number_segments_in_pupil = CONFIG_INI.getint(config_id,
                                                              'active_number_of_segments')
            if len(self.segments_in_pupil) != self.number_segments_in_pupil:
                raise ValueError("The array length active_segment_list does not match the active_number_of_segments in the config.ini. Please update your config.ini.")
        except NoOptionError:
            self.segments_in_pupil = iris_util.iris_pupil_naming()

        self.apply_flat_map = apply_flat_map
        self.data = iris_util.create_zero_array(self.number_segments_in_pupil)
        self.command = None


    def read_new_command(self, segment_values):
        """
        Read a new command and assign to the attribute 'data'

        :param segment_values: str, array. Can be .PTT111, .ini files or array where the first
                               element of the array is the center of the pupil and subsequent
                               elements continue up and clockwise around the pupil (see README
                               for more information) of the form {seg: (piston, tip, tilt)}
        """
        self.data = self.read_command(segment_values)


    def read_command(self, segment_values):
        """
        Read a command from one of the allowed formats

        :param segment_values: str, array. Can be .PTT111, .ini files or array where the first
                               element of the array is the center of the pupil and subsequent
                               elements continue up and clockwise around the pupil (see README
                               for more information) of the form {seg: (piston, tip, tilt)}
        """
        ptt_arr, segment_names = iris_util.read_segment_values(segment_values)
        if segment_names is not None:
            command_array = []
            for seg_name in self.segments_in_pupil:
                ind = np.where(np.asarray(segment_names) == seg_name)[0][0]
                command_array.append(ptt_arr[ind])
        else:
            command_array = ptt_arr

        return command_array


    def get_data(self):
        """ Grab the current shape to be applied to the DM (does NOT include the flat map)
        """
        return self.data


    def to_command(self):
        """ Output command suitable for sending to the hardware driver. The flat
        map will be added only at this stage
        """
        # Apply Flat Map
        if self.apply_flat_map:
            self.add_map(self.filename_flat)
        command_dict = dict(zip(self.segments_in_pupil, self.data))

        return command_dict


    def update_one_segment(self, segment_ind, ptt_tuple):
        """ Update the value of one segment. This will be ADDED to the current value

        :param segment_ind: int, the index of the segment in the pupil to be updated
                            (see README for relationship between index and segment)
        :param ptt_tuple: tuple with three values for piston, tip, and tilt

        """
        command_array = iris_util.create_zero_array(self.number_segments_in_pupil)
        command_array[segment_ind] = ptt_tuple

        self.add_map(command_array)


    def add_map(self, segment_values_to_add):
        """
        Add a command to the one already loaded.

        :param new_command: str or array (.PTT111 or .ini file, or array from POPPY)
        """
        original_data = self.get_data()
        new_data = self.read_command(segment_values_to_add)

        #TODO check for nans and handle them
        self.data = [tuple(map(sum, zip(orig, new))) for orig,
                                                         new in zip(original_data, new_data)]


def load_command(segment_values, apply_flat_map=True, config_id='iris_ao'):
    """
    Loads the segment_values from a file, array, or dictionary and returns a
    SegmentedDmCommand object.

    There are only two allowed segment mappings for the input formats, Native and Centered Pupil.
    See the README for the Iris AO for more details.

    :param segment_values: str or dict. Can be .PTT111, .ini files,
                           array from POPPY, or dictionary of the same form as the output
    :param apply_flat_map: Apply a flat map in addition to the data.

    :return: SegmentedDmCommand object representing the command dictionary.
    """
    dm_command_obj = SegmentedDmCommand(apply_flat_map=apply_flat_map, config_id=config_id)
    dm_command_obj.read_new_command(segment_values)

    return dm_command_obj


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
    def __init__(self, global_coefficients, convert_array_to_iris_units=True):
        # Grab pupil-specific values from config
        self.flat_to_flat = CONFIG_INI.getfloat('iris_ao', 'flat_to_flat_mm')  # [mm]
        self.gap = CONFIG_INI.getint('iris_ao', 'gap_um')  # [um]
        self.num_segs_in_pupil = CONFIG_INI.getint('iris_ao', 'active_number_of_segments')
        self.outer_ring_corners = CONFIG_INI.getboolean('iris_ao', 'include_outer_ring_corners')
        self.wavelength = (CONFIG_INI.getint('thorlabs_source_mcls1', 'lambda_nm')*u.nm).to(u.m)

        self.radius = (self.flat_to_flat/2*u.mm).to(u.m)
        self.num_terms = (self.num_segs_in_pupil - 1) * 3
        self.num_rings = get_num_rings(self.num_segs_in_pupil, self.outer_ring_corners)
        self.segment_list = get_segment_list(self.num_rings, center_segment=True,
                                             outer_corners=True)

        self.global_coefficients = global_coefficients
        self.convert_array_to_iris_units = convert_array_to_iris_units

        # Create the specific basis for this pupil
        self.basis = self.create_ptt_basis()

        # Create array of coefficients
        self.array_of_coefficients = self.get_array_from_global()


    def create_ptt_basis(self):
        #TODO: add segment list
        """
        Create the basis needed for getting the per/segment coeffs back

        :return: Poppy Segment_PTT_Basis object for the specified pupil
        """
        pttbasis = poppy.zernike.Segment_PTT_Basis(rings=self.num_rings,
                                                   flattoflat=self.flat_to_flat,
                                                   gap=self.gap,
                                                   segmentlist=self.segment_list)
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


    def to_dm_array(self):
        """
        Convert the array into an array that can be passed to the SegmentDmCommand
        """
        input_array = self.array_of_coefficients
        if self.convert_array_to_iris_units:
            input_array = iris_util.convert_dict_from_si(input_array)
        coeffs_array = match_ptt_values(input_array)

        return coeffs_array


def match_ptt_values(ptt_arr, decimals=3):
    """
    Make sure that the PTT coefficients are in the correct order for what is expected
    on the IrisAO and are rounded to a reasonable number of decimals

    :param ptt_arr: ndarray or list, of tuples existing of piston, tip, tilt,
                    values for each segment in a pupil
    """
    return [(np.round(ptt[0], decimals), -1*np.round(ptt[2], decimals),
             np.round(ptt[1], decimals)) for ptt in ptt_arr]


def poppy_numbering():
    """
    Numbering of the pupil in POPPY. Specifically for a 37 segment Iris AO
    """
    return np.arange(163)


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


def get_num_rings(number_segments_in_pupil, outer_ring_corners=True, max_rings=7):
    """
    Get the number of rings based on the number of specified segments using the
    number_segments_in_pupil and include_outer_ring_corners parameters. This can
    be used for a pupil of up to 7 rings (the max allowed in the PTT489 IrisAO model).
    Note that for the PTT489 model the 7th ring does not include the corner segments
    which you will need to make clear.

    :param number_segs_in_pupil: int, the number of segments in the pupil.
    :param outer_ring_corners: bool, True: include the corner segments in the outer
                               in the pupil - e.g. JWST pupil
                               False: do not include corner segments in
                               ring - e.g. LUVOIR A and LUVOIR B pupils
    :return: num_rings: int, the number of full rings of hexagonal segments in the pupil
    """
    # seg_nums: number of segments in a pupil of the corresponding # of rings
    seg_nums = [1,] # account for center segment
    for i in (np.arange(max_rings)+1):
        seg_nums.append(seg_nums[i-1]+i*6)

    if not outer_ring_corners:
        seg_nums = [num-6 if num > 6 else num for num in seg_nums]

    if number_segments_in_pupil not in seg_nums:
        raise Exception("Invalid number of segments give number_segments_in_pupil and include_outer_ring_corners parameters.")

    # The number of rings
    ring_nums = np.arange(max_rings+1)
    num_rings = [rings for segs, rings in zip(seg_nums,
                                              ring_nums) if number_segments_in_pupil == segs][0]
    return num_rings


def number_segments_in_rings(num_rings):
    """
    Determine number of segments in an aperture based on number of rings,
    existence of a center segment, and if it includes the corners on the outer-most ring

    :param rings: int, number of

    """
    num_segs = 1
    for ring in np.arange(num_rings)+1:
        num_segs += 6*ring

    return num_segs


def get_segment_list(num_rings, center_segment=True, outer_corners=True):
    """
    Always include center segment?? ugh
    """
    num_segs = number_segments_in_rings(num_rings)
    seglist = np.arange(num_segs)

    if not outer_corners:
        inner_segs = seglist[:(num_segs-6*num_rings)]
        outer_segs = seglist[(num_segs-6*num_rings):]
        outer_segs = np.delete(outer_segs, np.arange(0, outer_segs.size, num_rings)) # delete corner segs
        seglist = np.concatenate((inner_segs, outer_segs))

    if not center_segment:
        seglist = seglist[1:]
    return seglist


def create_aperture(segment_list=None, center_segment=True,
                    outer_corners=True):
    """
    """
    num_rings = get_num_rings(CONFIG_INI.getint('iris_ao', 'active_number_of_segments'))
    flat_to_flat = CONFIG_INI.getfloat('iris_ao', 'flat_to_flat_mm') * u.mm
    gap = CONFIG_INI.getfloat('iris_ao', 'gap_um') * u.micron

    if segment_list is None:
        segment_list = get_segment_list(num_rings, center_segment=center_segment,
                                        outer_corners=outer_corners)

    iris = poppy.dms.HexSegmentedDeformableMirror(name='Iris DM',
                                                  rings=num_rings,
                                                  flattoflat=flat_to_flat,
                                                  gap=gap,
                                                  segmentlist=segment_list)


def display(segment_values, instrument_fov,
            segment_mapping=None, wavefront=True, psf=True, out_dir=''):
    """
    Display the wavefront or expected psf generated by this wavefront

    :param segment_values: str, dict. Can be .PTT111, .ini files or dictionary of the
                            form {seg: (piston, tip, tilt)}
    :param instrument_fov: int, instrument field of view in arsecs
    :param active_segment_list: list, Numbers of the segments that are actively controlled
    :param segment_mapping: str or None. If None, this will be determined by input type of
                            segment_values (see list above). If you know that the default
                            is incorrect, you can overwrite with "native" or "centered"
                            depending on if the segment values are in the native (Iris)
                            numbering system, or if the are centered in the middle of the
                            pupil (start at 0).
    :param wavefront: bool, whether or not to display the wavefront
    :param psf: bool, whether or not to display the expected PSF from the wavefront commanded
    :param out_dir: str, location where the figures should be saved.
    """
    if segment_values is None:
        raise ValueError('segment_values cannot be None')

    num_rings = get_num_rings(CONFIG_INI.getint('iris_ao', 'active_number_of_segments'))
    flat_to_flat = CONFIG_INI.getfloat('iris_ao', 'flat_to_flat_mm') * u.mm
    gap = CONFIG_INI.getfloat('iris_ao', 'gap_um') * u.micron
    wavelength = (CONFIG_INI.getint('thorlabs_source_mcls1', 'lambda_nm')*u.nm)

    pixelscale = instrument_fov/512. # arcsec/px, 512 is size of image

    # read_segment_values returns the data and whether or not to convert into
    #native/Iris mapping, in this case we want to know if it's in centered mapping
    # convert_to_native_mapping = centered_mapping
    data, centered_mapping = iris_util.read_segment_values(segment_values)
    # Shift TO Poppy from the Iris AO
    if not active_segment_list:
        active_segment_list = iris_util.iris_pupil_naming()
    # command = data if centered_mapping else shift_command(data,
    #                                                       poppy_numbering()[:len(active_segment_list)],
    #                                                       active_segment_list)
    iris = poppy.dms.HexSegmentedDeformableMirror(name='Iris DM',
                                                  rings=num_rings,
                                                  flattoflat=flat_to_flat,
                                                  gap=gap)

    iris = deploy_global_wf(iris, data) # takes pupil and dictionary

    if wavefront:
        plt.figure()
        iris.display(what='opd', title='Shape put on the active segments')
        plt.savefig(os.path.join(out_dir, 'shape_on_dm.png'))

    if psf:
        plt.figure()
        osys = poppy.OpticalSystem()
        osys.add_pupil(iris)
        osys.add_detector(pixelscale=pixelscale, fov_arcsec=instrument_fov)

        psf = osys.calc_psf(wavelength=wavelength)
        poppy.display_psf(psf, vmin=10e-8, vmax=10e-2,
                          title='PSF created by the shape put on the active segments')
        plt.savefig(os.path.join(out_dir, 'simulated_psf.png'))
