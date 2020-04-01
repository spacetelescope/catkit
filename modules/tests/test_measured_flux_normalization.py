import os
import pytest

from astropy.table import QTable
from astropy.io import fits
import numpy as np

from hicat.experiments.modules.measured_flux_normalization import get_normalization_factor
from hicat.experiments.modules.measured_flux_normalization import satellite_photometry

import hicat.util


def test_get_normalization_factor():
    """Test that the factor is a positive number."""

    column_names = ['id', 'xcenter', 'ycenter', 'aperture_sum', 'fwhm', 'aperture_radius', 'color_filter', 'nd_filter']

    coron_im = 'coron_image_cal.fits'
    direct_im = 'direct_image_cal.fits'

    file_location = os.path.join(hicat.util.find_repo_location(), 'hicat', 'experiments', 'modules', 'tests')

    direct_table, coron_table, factor = get_normalization_factor(os.path.join(file_location, coron_im),
                                                                 os.path.join(file_location, direct_im),
                                                                 out_path='',
                                                                 apodizer='no_apodizer')

    # These need to be QTables
    assert isinstance(direct_table, QTable), 'direct_table is no astropy.QTable'
    assert isinstance(coron_table, QTable), 'coron_table is no astropy.QTable'

    # We rely on proper naming of the columns
    assert direct_table.keys() == column_names, 'Column names in direct_table are wrong.'
    assert coron_table.keys() == column_names, 'Column names in coron_table are wrong.'

    # One result per image pair only
    assert len(direct_table) == 1, 'More than one photometric result in direct_table.'
    assert len(coron_table) == 1, 'More than one photometric result in coron_table.'

    # If the resulting normalization factor is negative, something is terribly off
    assert factor > 0, 'Flux normalization factor cannot be negative.'


def test_satellite_photometry():
    """Test that the extracted aperture is in the image boundaries"""

    column_names = ['id', 'xcenter', 'ycenter', 'aperture_sum', 'fwhm', 'aperture_radius']

    coron_im = 'coron_image_cal.fits'
    direct_im = 'direct_image_cal.fits'

    file_location = os.path.join(hicat.util.find_repo_location(), 'hicat', 'experiments', 'modules', 'tests')

    direct_img_data = fits.getdata(os.path.join(file_location, direct_im))
    coron_img_data = fits.getdata(os.path.join(file_location, coron_im))

    direct_table = satellite_photometry(direct_img_data, 'direct', output_path='', save_fig=False)
    coron_table = satellite_photometry(coron_img_data, 'coron', output_path='', save_fig=False)

    # These need to be QTables
    assert isinstance(direct_table, QTable), 'direct_table is no astropy.QTable'
    assert isinstance(coron_table, QTable), 'coron_table is no astropy.QTable'

    # We rely on proper naming of the columns
    assert direct_table.keys() == column_names, 'Column names in direct_table are wrong.'
    assert coron_table.keys() == column_names, 'Column names in coron_table are wrong.'

    # One result per image pair only
    assert len(direct_table) == 1, 'More than one photometric result in direct_table.'
    assert len(coron_table) == 1, 'More than one photometric result in coron_table.'

    # Aperture does not extend off the direct image in x or y
    assert (direct_table['xcenter'].value[0] + direct_table['aperture_radius'][0]) < np.shape(direct_img_data)[1], \
        'Aperture extends beyond maximum x range of image'
    assert (direct_table['xcenter'].value[0] - direct_table['aperture_radius'][0]) > 0, 'Aperture extends beyond ' \
                                                                                        'minimum x range of image '
    assert (direct_table['ycenter'].value[0] + direct_table['aperture_radius'][0]) < np.shape(direct_img_data)[0], \
        'Aperture extends beyond maximum y range of image'
    assert (direct_table['ycenter'].value[0] - direct_table['aperture_radius'][0]) > 0, 'Aperture extends beyond ' \
                                                                                        'minimum y range of image '

    # Aperture does not extend off the coron image in x or y
    assert (coron_table['xcenter'].value[0] + coron_table['aperture_radius'][0]) < np.shape(coron_img_data)[1], \
        'Aperture extends beyond maximum x range of image'
    assert (coron_table['xcenter'].value[0] - coron_table['aperture_radius'][0]) > 0, 'Aperture extends beyond ' \
                                                                                      'minimum x range of image '
    assert (coron_table['ycenter'].value[0] + coron_table['aperture_radius'][0]) < np.shape(coron_img_data)[0], \
        'Aperture extends beyond maximum y range of image'
    assert (coron_table['ycenter'].value[0] - coron_table['aperture_radius'][0]) > 0, 'Aperture extends beyond ' \
                                                                                      'minimum y range of image '