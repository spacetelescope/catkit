import os

from astropy.stats import sigma_clipped_stats
from astropy.table import QTable
import hcipy
import logging
from matplotlib.colors import LogNorm
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
from photutils import aperture_photometry
from photutils import CircularAperture
from photutils import DAOStarFinder

import hicat.util
log = logging.getLogger(__name__)


def satellite_photometry(data, im_type, output_path='', sigma=8.0, save_fig=True, zoom_in=False):
    """
    Performs source detection and extraction on 'data' within spatial limits.
    :param data: array, image to analyze
    :param im_type: string, 'direct' or 'coron' (only used to name plot)
    :param output_path: string, path to save outputs to
    :param sigma: float, number of stddevs for clipping limit
    :param save_fig: bool, toggle to save figures
    :param zoom_in: bool, saves a cropped image with the aperture in more detail
    :return: astropy.table.table.Qtable, photometry table of input image
    """
    # Cast to numpy.array if it's an hcipy.Field
    if isinstance(data, hcipy.Field):
        data = np.array(data.shaped)

    # Scale distances and source detection parameters via img shape.
    im_shape = np.shape(data)
    fwhm = int(np.round(im_shape[0] * 0.03))      #TODO: HICAT-770
    radius = int(np.round(im_shape[0] * 0.045))   #TODO: HICAT-770

    # Find sources in entire image.
    mean, median, std = sigma_clipped_stats(data, sigma=sigma)
    daofind = DAOStarFinder(fwhm=fwhm, threshold=30 * std)    #TODO: HICAT-770

    # Mask out all sources except upper-middle satellite source.
    mask = np.zeros(data.shape, dtype=bool)
    mask[int(np.round(im_shape[0] * 0.82)):, 0:int(np.round(im_shape[1] * 0.34))] = True    #TODO: HICAT-770
    mask[0:int(np.round(im_shape[0] * 0.82)), :] = True    #TODO: HICAT-770
    mask[int(np.round(im_shape[0] * 0.82)):, int(np.round(im_shape[1] * 0.68)):] = True    #TODO: HICAT-770
    # Detect sources
    sources = daofind(data, mask=mask)

    # Transpose to have xy-pairs (x,y), especially if there are multiple sources.
    positions = np.transpose((sources['xcentroid'], sources['ycentroid']))
    apertures = CircularAperture(positions, r=radius)
    phot_table = aperture_photometry(data, apertures)
    phot_table['fwhm'] = fwhm
    phot_table['aperture_radius'] = radius

    # Adjust for multiple source detections. This should not occur often with adjusted parameters.
    if len(phot_table) > 1:
        log.warning('Multiple elligible sources found initially. Brightest will be selected.')
        phot_table = phot_table[phot_table['aperture_sum'] == phot_table['aperture_sum'].max()]
        coord_list = [phot_table['xcenter'].value[0], phot_table['ycenter'].value[0]]
        positions = np.array([coord_list])
        apertures = CircularAperture(positions, r=radius)

    if save_fig:
        fig = plt.figure(figsize=(5, 5))

        if zoom_in:
            plt.ylim(sources['ycentroid'] - fwhm * 2, sources['ycentroid'] + fwhm * 2)
            plt.xlim(sources['xcentroid'] - fwhm * 2, sources['xcentroid'] + fwhm * 2)

        im = plt.imshow(data, norm=LogNorm())
        apertures.plot(color='red', lw=1.5, alpha=1)

        cbar_ax = fig.add_axes([0.9, 0.125, 0.05, 0.755])
        fig.colorbar(im, cax=cbar_ax)

        fig.savefig(os.path.join(output_path, 'photometry-{}.pdf'.format(im_type)), dpi=100, bbox_inches='tight')
        plt.close(fig)

    return phot_table


def rectangle_photometry(data, im_type, output_path='', save_fig=True):
    """
    Performs source detection and extraction on 'data' within spatial limits.
    :param data: array, image to analyze
    :param im_type: string, 'direct' or 'coron' (only used to name plot)
    :param output_path: string, path to save outputs to
    :param save_fig: bool, toggle to save figures
    :return: astropy.table.table.Qtable, photometry table of input image
    """
    # Cast to numpy.array if it's an hcipy.Field
    if isinstance(data, hcipy.Field):
        data = np.array(data.shaped)

    # Scale distances and source detection parameters via img shape.
    im_shape = np.shape(data)
    y_limits = (int(np.round(im_shape[0] * 0.78)), int(np.round(im_shape[0] - 0.05 * (im_shape[0]))))   #TODO: HICAT-770
    x_limits = (int(np.round(im_shape[1] * 0.32)), int(np.round(im_shape[1] * 0.68)))    #TODO: HICAT-770

    region_sum = np.sum(data[y_limits[0]:y_limits[1], x_limits[0]:x_limits[1]])
    region_table = QTable(data=[[region_sum], [x_limits], [y_limits]], masked=False,
                          names=('aperture_sum', 'x_limits', 'y_limits'))

    if save_fig:
        fig, ax = plt.subplots(1)
        fig.set_figheight(5)
        fig.set_figwidth(5)

        im = ax.imshow(data, norm=LogNorm())

        # Create a Rectangle patch
        rect = patches.Rectangle((x_limits[0], y_limits[0]), x_limits[1] - x_limits[0], y_limits[1] - y_limits[0], lw=1.5, alpha=1,
                                 edgecolor='r', facecolor='none')

        # Add the patch to the Axes
        ax.add_patch(rect)

        cbar_ax = fig.add_axes([0.9, 0.125, 0.05, 0.755])
        fig.colorbar(im, cax=cbar_ax)

        fig.savefig(os.path.join(output_path, f'photometry-{im_type}.pdf'), dpi=300, bbox_inches='tight')
        plt.close(fig)

    return region_table


def calc_attenuation_factor(coron_data, direct_data, out_path, apodizer='no_apodizer'):
    """
    Calculate flux attenuation factor for direct and coron data.

    The HiCAT direct images are taken with an ND filter, which includes some losses due to the fiber coupling, when
    using the light source assembly (LSA). Calculate the attenuation caused by the ND filter and the fiber coupling
    by comparing the count rates in a well-exposed direct image (ND + coupling) and a well-exposed coron image (no ND
    and no coupling).

    In CLC mode, perform aperture photometry on the central top satellite spot in direct and coron image, and the
    returned flux attenuation factor for the direct image is the sum of pixels in aperture in coron / sum of pixels
    over aperture in direct. This also means that this attenuation factor equals 1 for coron by definition and does
    hence not need to be calculated.

    In APLC mode, we do the same except that we measure the flux in an area in the outer part of the images as opposed
    to an aperture over a satellite spot.

    :param coron_data: tuple or string, (img, header) Pass a tuple of the coron img and header; or filepath to image.
    :param direct_data: tuple or string, (img, header) Pass a tuple of the direct img and header; or filepath to image.
    :param out_path: string, path to save outputs to
    :param apodizer: string, 'no_apodizer' or one of the apodizers (e.g. 'cnt2_apodizer')
    :return: photometry tables for direct and coron (astropy.table.table.Qtable), and flux attenuation factor (float)
    """

    # Unpack image and header
    coron_img, coron_header = hicat.util.unpack_image_data(coron_data)
    direct_img, direct_header = hicat.util.unpack_image_data(direct_data)

    # Read filter info
    color_filter_coron, nd_filter_coron = coron_header['FILTERS'].split(',')
    color_filter_direct, nd_filter_direct = direct_header['FILTERS'].split(',')

    # Get photometry
    photometry_func = satellite_photometry if apodizer == 'no_apodizer' else rectangle_photometry
    coron_table = photometry_func(data=coron_img, im_type=f'coron-{nd_filter_coron}-{color_filter_coron}',
                                  output_path=out_path)
    direct_table = photometry_func(data=direct_img, im_type=f'direct-{nd_filter_direct}-{color_filter_direct}',
                                   output_path=out_path)
    if len(coron_table) != 1:
        log.warning('Likely Problem with coronagraphic img satellite photometry')

    if len(direct_table) != 1:
        log.warning('Likely Problem with direct img satellite photometry')

    # Add filter info to photometry tables
    coron_table['color_filter'] = color_filter_coron
    coron_table['nd_filter'] = nd_filter_coron
    direct_table['color_filter'] = color_filter_direct
    direct_table['nd_filter'] = nd_filter_direct

    # Extract count rates
    coron_countrate = coron_table['aperture_sum'][0]
    direct_countrate = direct_table['aperture_sum'][0]

    # Calculate flux attenuation factor
    attenuation_factor = coron_countrate / direct_countrate  # type: float

    return direct_table, coron_table, attenuation_factor
