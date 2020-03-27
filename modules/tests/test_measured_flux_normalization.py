import os
import pytest

from astropy.table import QTable

from hicat.experiments.modules.measured_flux_normalization import get_normalization_factor
import hicat.util


def test_get_normalization_factor():
    """Test that the factor is a positive number."""

    column_names = ['id', 'xcenter', 'ycenter', 'aperture_sum', 'color_filter', 'nd_filter']

    coron_im = 'coron_image_cal.fits'
    direct_im = 'direct_image_cal.fits'

    file_location = os.path.join(hicat.util.find_repo_location(), 'hicat', 'experiments', 'modules', 'tests')

    direct_table, coron_table, factor = get_normalization_factor(os.path.join(file_location, coron_im),
                                                                 os.path.join(file_location, direct_im),
                                                                 out_path='',
                                                                 apodizer='no_apodizer')

    # These need to be QTables
    assert type(direct_table) == QTable, 'direct_table is no astropy.QTable'
    assert type(coron_table) == QTable, 'coron_table is no astropy.QTable'

    # We rely on proper naming of the columns
    assert direct_table.keys() == column_names, 'Column names in direct_table are wrong.'
    assert coron_table.keys() == column_names, 'Column names in coron_table are wrong.'

    # One result per image pair only
    assert len(direct_table) == 1, 'More than one photometric result in direct_table.'
    assert len(coron_table) == 1, 'More than one photometric result in coron_table.'

    # If the resulting normalization factor is negative, something is terribly off
    assert factor > 0, 'Flux normalization factor cannot be negative.'
