"""
Create a command (in POPPY: wavefront error) using POPPY for your pupil.
Right now, this is limited to global shapes.

To use to get command for the Iris AO:

  coeffs_array = create_coeffs_from_global(coeff_global)
  iris_command_obj = segmented_dm_command.load_command(coeffs_array)

"""

import astropy.units as u
import poppy
import numpy as np

from catkit.config import CONFIG_INI

FLAT_TO_FLAT = CONFIG_INI.getfloat('iris_ao', 'flat_to_flat')  # in [mm]
GAP_UM = CONFIG_INI.getint('iris_ao', 'gap_um')
NUM_SEGS_IN_PUPIL = CONFIG_INI.getint('iris_ao', 'pupil_nb_seg')

RADIUS = 0.003525 * u.m #TODO: radius of a segment - CONFIG FILE = FLAT_TO_FLAT/2
LAMBDA = (CONFIG_INI.getint('thorlabs_source_mcls1', 'lambda_nm')*u.nm).to(u.m)

NTERMS = (NUM_SEGS_IN_PUPIL - 1) * 3


def get_num_rings():
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

    if NUM_SEGS_IN_PUPIL not in seg_nums:
        raise Exception("Invalid number of segments for number_segments_in_pupil.")

    num_rings = [rings for segs, rings in zip(seg_nums,
                                              ring_nums) if NUM_SEGS_IN_PUPIL == segs][0]
    return num_rings


def create_wavefront_from_global(coeff_global):
    """
    Given an array of global coefficients, create wavefront
    """
    wavefront = poppy.ZernikeWFE(radius=RADIUS, coefficients=coeff_global)
    # Sample the WFE onto an actual array
    wavefront_out = wavefront.sample(wavelength=LAMBDA, grid_size=2*RADIUS,
                                     npix=512, what='opd')

    return wavefront_out


def create_ptt_basis():
    """
    Create the basis needed for getting the per/segment coeffs back
    """
    pttbasis = poppy.zernike.Segment_PTT_Basis(rings=get_num_rings(),
                                               flattoflat=FLAT_TO_FLAT,#2 * rad * u.mm,
                                               gap=GAP_UM)
    return pttbasis


def get_coeffs_from_pttbasis(basis, wavefront):
    """
    From a the speficic pttbasis, get back the coeff_array that will be sent as
    a command to the Iris AO
    """
    coeff_array = poppy.zernike.opd_expand_segments(wavefront, nterms=NTERMS, basis=basis)
    coeff_array = np.reshape(coeff_array, (NUM_SEGS_IN_PUPIL - 1, 3))

    return coeff_array


def get_wavefront_from_coeffs(basis, coeff_array):
    """
    Get the wavefront from the coefficients based on the basis given
    """
    wavefront = poppy.zernike.opd_from_zernikes(coeff_array, basis=basis)

    return wavefront


def create_coeffs_from_global(coeff_global):
    """
    From a global coeff array, get back the per-segment coefficient array

    :param coeff_global: Array of global coefficents

    :returns coeffs_array: Array of coefficients for Piston, Tip, and Tilt, for your pupil
    """
    wavefront = create_wavefront_from_global(coeff_global)
    pttbasis = create_ptt_basis()
    coeffs_array = get_coeffs_from_pttbasis(pttbasis, wavefront)

    return coeffs_array
