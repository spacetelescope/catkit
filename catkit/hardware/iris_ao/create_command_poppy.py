"""
Create a command (in POPPY: wavefront error) using POPPY for your pupil.
Right now, this is limited to global shapes.

To use to get command for the Iris AO:

  poppy_obj = PoppySegmentedCommand(global_coefficients)
  coeffs_array = poppy_obj.to_array()
  iris_command_obj = segmented_dm_command.load_command(coeffs_array)

"""

import astropy.units as u
import poppy
import numpy as np

from catkit.config import CONFIG_INI


class PoppySegmentedCommand(object):
    """
    Create an array of piston, tip, tilt values for each segment in the pupil
    """
    def __init__(self, global_coefficients):
        # Grab pupil-specific values from config
        self.flat_to_flat_mm = CONFIG_INI.getfloat('iris_ao', 'flat_to_flat')  # [mm]
        self.gap_um = CONFIG_INI.getint('iris_ao', 'gap_um')  # [um]
        self.num_segs_in_pupil = CONFIG_INI.getint('iris_ao', 'pupil_nb_seg')
        self.wavelength = (CONFIG_INI.getint('thorlabs_source_mcls1', 'lambda_nm')*u.nm).to(u.m)

        self.radius = (self.flat_to_flat_mm/2*u.mm).to(u.m)
        self.num_terms = (self.num_segs_in_pupil - 1) * 3

        self.global_coefficients = global_coefficients

        # Create the specific basis for this pupil
        self.basis = self.create_ptt_basis()


    def create_ptt_basis(self):
        """
        Create the basis needed for getting the per/segment coeffs back
        """
        pttbasis = poppy.zernike.Segment_PTT_Basis(rings=get_num_rings(self.num_segs_in_pupil),
                                                   flattoflat=self.flat_to_flat_mm,
                                                   gap=self.gap_um)
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
