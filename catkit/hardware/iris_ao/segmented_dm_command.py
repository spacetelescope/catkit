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


class SegmentedDmCommand():
    """
    Handles converting inputs into expected dictionary format to be sent to the Iris AO.
    Does NOT interact with hardware directly.

    :attribute data: dict, Input data, shifted if custom pupil exists in config file
    :attribute apply_flat_map: bool, whether or not to apply the flat map
    :attribute source_pupil_numbering: list, numbering native to data
    :attribute command: dict, Final command with flat if apply_flat_map = True
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
        self.data = iris_util.create_zero_array(self.number_segments_in_pupil) #TODO: change this to Nans?
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
            for seg_name in self.segments_in_pupil:  # Pull out only segments in the pupil
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
def poppy_numbering():
    """
    Numbering of the pupil in POPPY. Specifically for a 37 segment Iris AO
    """
    return np.arange(163)


def match_ptt_values(ptt_arr, decimals=3):
    """
    Make sure that the PTT coefficients are in the correct order for what is expected
    on the IrisAO and are rounded to a reasonable number of decimals

    :param ptt_arr: ndarray or list, of tuples existing of piston, tip, tilt,
                    values for each segment in a pupil
    """
    return [(np.round(ptt[0], decimals), -1*np.round(ptt[2], decimals),
             np.round(ptt[1], decimals)) for ptt in ptt_arr]


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


class SegmentedAperture():
    """
    Create a segmented aperture with Poppy using the parameters for the testbed
    and segmented DM from the config.ini file.

    :param dm_config_id: str, name of the section in the config_id where information
                         regarding the segmented DM can be found. Default: 'iris_ao'
    :param laser_config_id: str, name of the section in the config_id where information
                         regarding the laser can be found. Default: 'thorlabs_source_mcls1'
    """
    def __init__(self, dm_config_id='iris_ao',
                 laser_config_id='thorlabs_source_mcls1'):

        # Parameters specific to testbed setup being used
        self.wavelength = (CONFIG_INI.getint(laser_config_id, 'lambda_nm')*u.nm)

        # Parameters specifc to the aperture and segmented DM being used
        self.outer_ring_corners = CONFIG_INI.getboolean(dm_config_id, 'include_outer_ring_corners')
        self.center_segment = CONFIG_INI.getboolean(dm_config_id, 'include_center_segment')
        self.flat_to_flat = CONFIG_INI.getfloat(dm_config_id, 'flat_to_flat_mm') * u.mm
        self.gap = CONFIG_INI.getfloat(dm_config_id, 'gap_um') * u.micron
        self.num_segs_in_pupil = CONFIG_INI.getint('iris_ao', 'active_number_of_segments')

        # Get the specific segments
        self.num_rings = self.get_number_of_rings()
        self.segment_list = self.get_segment_list()


    def create_aperture(self):
        """
        Based on values in config file, create the aperture to be simulated

        :returns: A Poppy HexSegmentedDeformableMirror object for this aperture
        """
        aperture = poppy.dms.HexSegmentedDeformableMirror(name='Iris DM',
                                                          rings=self.num_rings,
                                                          flattoflat=self.flat_to_flat,
                                                          gap=self.gap,
                                                          segmentlist=self.segment_list)
        return aperture


    def get_segment_list(self):
        """
        Grab the list of segments to be used in your pupil taking into account if your
        aperture has a center segment and/or the segments in the corners of the outer ring.
        This list is passed to Poppy to help create the aperture.

        :param num_rings: int, The number of rings in your pupil
        :return: list, the list of segments
        """
        num_segs = self.number_segments_in_aperture(self.num_rings)
        seglist = np.arange(num_segs)

        if not self.outer_ring_corners:
            inner_segs = seglist[:(num_segs-6*self.num_rings)]
            outer_segs = seglist[(num_segs-6*self.num_rings):]
            outer_segs = np.delete(outer_segs, np.arange(0, outer_segs.size,
                                                         self.num_rings)) # delete corner segs
            seglist = np.concatenate((inner_segs, outer_segs))

        if not self.center_segment:
            seglist = seglist[1:]
        return seglist


    def get_number_of_rings(self, max_rings=7):
        """
        Get the number of rings based on the number of active segments specified in the
        config.ini file. This function can be used for a pupil of up to 7 rings (the max
        allowed in the PTT489 IrisAO model).
        Note that for the PTT489 model the 7th ring does not include the corner segments
        which you will need to make clear.

        :returns: num_rings: int, the number of full rings of hexagonal segments in the aperture
        """
        segs_per_ring = SegmentedAperture.number_segments_in_aperture(max_rings, return_list=True)

        # If no outer corners, you will have 6 fewer segments in that outer ring
        if not self.outer_ring_corners:
            segs_per_ring = [num-6 if num > 6 else num for num in segs_per_ring]
        # If no center segment, you will have 1 fewer segment overall
        if not self.center_segment:
            segs_per_ring = [num-1 for num in segs_per_ring]

        try:
            num_rings = segs_per_ring.index(self.num_segs_in_pupil)
        except ValueError:
            raise ValueError("Invalid number of segments. Please check your config.ini file.")

        return num_rings


    @staticmethod
    def number_segments_in_aperture(number_of_rings=7, return_list=False):
        """
        For a segmented aperture of rings = number_of_rings, give the total number of
        segments in the aperture given an aperture of 1, 2, 3, etc. rings. Will return
        a list of the total number of segments in the *aperture* per ring where the ring
        is indicated by the index in the list.

        param: number_of_rings, int, the number of rings in the aperture

        returns: a list of segments where the index of the value corresponds to the
                 number of rings. For example: index 0 corresponds with the center
                 where there is one segment.
        """
        segs_per_ring = [1,] # number of segments per ring
        for i in np.arange(number_of_rings)+1:
            segs_per_ring.append(segs_per_ring[i-1]+i*6)

        if return_list:
            return segs_per_ring
        else:
            return segs_per_ring[number_of_rings]


class PoppySegmentedCommand(SegmentedAperture):
    """
    Create a segement values array (and dictionary) (in POPPY: wavefront error) using
    POPPY for your pupil. This is currently limited to global shapes. The out put is
    either a dictionary of piston, tip, tilt for each segment.

    This class inherits the SegmentedAperture class.

    To use to get command for the Iris AO:
      poppy_obj = PoppySegmentedCommand(global_coefficients)
      command_dict = poppy_obj.to_dm_array()
      iris_command_obj = segmented_dm_command.load_command(command_dict)

    :param global_coefficients: list of global zernike coefficients in the form
                                [piston, tip, tilt, defocus, ...] (Noll convention)
    """
    def __init__(self, global_coefficients, convert_array_to_iris_units=True,
                 dm_config_id='iris_ao', laser_config_id='thorlabs_source_mcls1'):
        SegmentedAperture.__init__(self, dm_config_id=dm_config_id, laser_config_id=laser_config_id)

        self.radius = (self.flat_to_flat/2).to(u.m)
        self.num_terms = (self.num_segs_in_pupil - 1) * 3

        self.global_coefficients = global_coefficients
        self.convert_array_to_iris_units = convert_array_to_iris_units

        # Create the specific basis for this pupil
        self.basis = self.create_ptt_basis()

        # Create array of coefficients
        self.array_of_coefficients = self.get_array_from_global()


    def create_ptt_basis(self):
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
            input_array = iris_util.convert_array(input_array)
        coeffs_array = match_ptt_values(input_array) # Only okay if it goes through SegmentedDmCommand first

        return coeffs_array


class DisplayCommand(SegmentedAperture):
    """
    For a Segmented DM command (specifically the PTT list per segment), display
    the wavefront or mirror state.

    This class inherits the SegmentedAperture class.

    :param ptt_list: list, SegmentedDmCommand.data or a list of PTT values
    :param out_dir: str, where to save figures
    :param dm_config_id: str, name of the section in the config_id where information
                         regarding the segmented DM can be found. Default: 'iris_ao'
    :param laser_config_id: str, name of the section in the config_id where information
                         regarding the laser can be found. Default: 'thorlabs_source_mcls1'

    :attr ptt_list:list, list of piston, tip, tilt values for each segment in aperture
    :attr out_dir: str, where to save figures
    :attr instrument_fov: int, The field of view of the camera being used
    :attr aperture: poppy.dms.HexSegmentedDeformableMirror object

    """
    def __init__(self, ptt_list, out_dir='', dm_config_id='iris_ao',
                 laser_config_id='thorlabs_source_mcls1', testbed_config_id='testbed'):
        SegmentedAperture.__init__(self, dm_config_id=dm_config_id, laser_config_id=laser_config_id)
        if ptt_list is None:
            raise ValueError('Your list of Piston, Tip, Tilt values cannot be None')

        # Check for and replace Nans
        bad = np.where(~np.isnan(ptt_list))[0]
        self.ptt_list = ptt_list
        self.out_dir = out_dir

        # Grab the FOV of the instrument from the config file
        self.instrument_fov = (CONFIG_INI.getint(testbed_config_id, 'fov'))

        # Create the aperture and apply the shape
        self.aperture = self.create_aperture()
        self.deploy_global_wf()


    def deploy_global_wf(self):
        """
        Put a global wavefront on the Iris AO, from an Iris AO dict input wavefront map.
        """
        matched_ptt_list = match_ptt_values(self.ptt_list) # take care of the tip/tilt swap in poppy

        for seg, values in zip(self.aperture.segmentlist, matched_ptt_list):
            # conversion from um and mrad to m and rad
            self.aperture.set_actuator(seg, values[0]*(u.um).to(u.m),
                                       values[1]*(u.mrad).to(u.rad),
                                       values[2]*(u.mrad).to(u.rad))


    def display(self, display_wavefront=True, display_psf=True):
        """
        Display either the deployed mirror state ("wavefront") or the PSF created
        by this mirror state.

        :params display_wavefront: bool, If true, display the deployed mirror state
        :params display_psf: bool, If true, display the simulated PSF created by the
                             mirror state
        """
        if display_wavefront:
            self.plot_wavefront()
        if display_psf:
            self.plot_psf()


    def plot_wavefront(self):
        """
        Plot the deployed mirror state ("wavefront")
        """
        plt.figure()
        self.aperture.display(what='opd', title='Shape put on the active segments')
        plt.savefig(os.path.join(self.out_dir, 'shape_on_dm.png'))


    def plot_psf(self):
        """
        Plot the simulated PSF based on the mirror state
        """
        pixelscale = self.instrument_fov/512. # arcsec/px, 512 is size of image
        plt.figure()
        osys = poppy.OpticalSystem()
        osys.add_pupil(self.aperture)
        osys.add_detector(pixelscale=pixelscale, fov_arcsec=self.instrument_fov)

        psf = osys.calc_psf(wavelength=self.wavelength)
        poppy.display_psf(psf, vmin=10e-8, vmax=10e-2,
                          title='PSF created by the shape put on the active segments')
        plt.savefig(os.path.join(self.out_dir, 'simulated_psf.png'))
