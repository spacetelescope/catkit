import os

from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.table import QTable
import hcipy
from matplotlib.colors import LogNorm
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
from photutils import aperture_photometry
from photutils import CircularAperture
from photutils import DAOStarFinder


def satellite_photometry(data, im_spec, output_path='', rad=8, sigma=3.0, fwhm=5., save_fig=True, zoom_in=False):
    """
    Performs source detection and extraction on 'data' within spatial limits.
    :param data: array, image to analyze
    :param im_spec: string, 'direct' or 'coron' (only used to name plot)
    :param output_path: string, path to save outputs to
    :param rad: int, radius of photometry aperture
    :param sigma: float, number of stddevs for clipping limit
    :param fwhm: float, full-width-half-max of source
    :param save_fig: bool, toggle to save figures
    :param zoom_in: bool, saves a cropped image with the aperture in more detail
    :return: astropy.table.table.Qtabl, photometry table of input image
    """
    # Cast to numpy.array if it's an hcipy.Field
    if type(data) == hcipy.field.field.Field:
        data = np.array(data.shaped)

    mean, median, std = sigma_clipped_stats(data, sigma=sigma)
    daofind = DAOStarFinder(fwhm=fwhm, threshold=7.*std)

    # Mask out all sources except top source - this region is for the binned 178 x 178 px HiCAT image
    mask = np.zeros(data.shape, dtype=bool)
    mask[145:178, 0:60] = True
    mask[0:145, 0:178] = True
    mask[145:178, 120:178] = True

    sources = daofind(data, mask=mask)
    positions = np.transpose((sources['xcentroid'], sources['ycentroid']))
    apertures = CircularAperture(positions, r=rad)

    phot_table = aperture_photometry(data, apertures)

    if save_fig:
        fig = plt.figure(figsize=(5, 5))

        plt.imshow(data, norm=LogNorm())
        plt.colorbar()
        if zoom_in:
            plt.ylim(sources['ycentroid'] - 15, 178)
            plt.xlim(sources['xcentroid'] - 15, sources['xcentroid'] + 15)

        apertures.plot(color='red', lw=1.5, alpha=1)
        fig.savefig(os.path.join(output_path, 'photometry-{}.pdf'.format(im_spec)), dpi=300, bbox_inches='tight')
        plt.close(fig)

    return phot_table


def rectangle_photometry(data, im_spec, x_lims=(7,60), y_lims=(7,171), output_path='', save_fig=True):
    """
    Performs source detection and extraction on 'data' within spatial limits.
    :param data: array, image to analyze
    :param im_spec: string, 'direct' or 'coron' (only used to name plot)
    :param x_lims: tuple (float), lower and upper x limits of extraction region.
    :param y_lims: tuple (float), lower and upper y limits of extraction region.
    :param output_path: string, path to save outputs to
    :param save_fig: bool, toggle to save figures
    :return: astropy.table.table.Qtabl, photometry table of input image
    """
    # Cast to numpy.array if it's an hcipy.Field
    if type(data) == hcipy.field.field.Field:
        data = np.array(data.shaped)

    region_sum = np.sum(data[y_lims[0]:y_lims[1],x_lims[0]:x_lims[1]])
    region_table = QTable(data=[[region_sum], [x_lims], [y_lims]], masked=False, names=('aperture_sum','x_lims','y_lims'))

    if save_fig:
        fig, ax = plt.subplots(1)
        fig.set_figheight(5)
        fig.set_figwidth(5)

        im = ax.imshow(data, norm=LogNorm())

        # Create a Rectangle patch
        rect = patches.Rectangle((x_lims[0],y_lims[0]), x_lims[1]-x_lims[0], y_lims[1]-y_lims[0], lw=1.5, alpha=1, edgecolor='r',facecolor='none')
        # Add the patch to the Axes
        ax.add_patch(rect)

        cbar_ax = fig.add_axes([0.9, 0.125, 0.05, 0.755])
        fig.colorbar(im, cax=cbar_ax)

        fig.savefig(os.path.join(output_path, 'photometry-{}.pdf'.format(im_spec)), dpi=300, bbox_inches='tight')
        plt.close(fig)

    return region_table


def get_normalization_factor(coron_data, direct_data, out_path, apodizer='no_apodizer'):
    """
    Calculate flux normalization factor for direct and coron data.
    :param coron_data: tuple or string, (img, header) Pass a tuple of the coron img and header; or filepath to image.
    :param direct_data: tuple or string, (img, header) Pass a tuple of the direct img and header; or filepath to image.
    :param out_path: string, path to save outputs to
    :param apodizer: string, 'no_apodizer' or 'cnt2_apodizer'
    :return: photometry tables for direct and coron (astropy.table.table.Qtable), and flux normalization factor (float)
    """
    if type(coron_data) == tuple:
        coron_header = coron_data[1]
        coron_img = coron_data[0]
    elif type(coron_data) == str:
        if os.path.exists(coron_data):
            coron_header = fits.getheader(coron_data)
            coron_img = fits.getdata(coron_data)
    else:
        raise TypeError('Invalid data reference for direct image passed.')

    if type(direct_data) == tuple:
        direct_header = direct_data[1]
        direct_img = direct_data[0]
    elif type(direct_data) == str:
        if os.path.exists(direct_data):
            direct_header = fits.getheader(direct_data)
            direct_img = fits.getdata(direct_data)
    else:
        raise TypeError('Invalid data reference for coronagraphic image passed.')

    # Read filter info
    color_filter_coron, nd_filter_coron = coron_header['FILTERS'].split(',')
    color_filter_dir, nd_filter_dir = direct_header['FILTERS'].split(',')

    # Get photometry
    if apodizer == 'cnt2_apodizer':
        coron_table = rectangle_photometry(data=coron_img, im_spec='coron-{}-{}'.format(nd_filter_coron, color_filter_coron), output_path=out_path)
        direct_table = rectangle_photometry(data=direct_img, im_spec='direct-{}-{}'.format(nd_filter_dir, color_filter_dir), output_path=out_path)

    elif apodizer == 'no_apodizer':
        coron_table = satellite_photometry(data=coron_img, im_spec='coron-{}-{}'.format(nd_filter_coron, color_filter_coron), output_path=out_path)
        direct_table = satellite_photometry(data=direct_img, im_spec='direct-{}-{}'.format(nd_filter_dir, color_filter_dir), output_path=out_path)
        if len(coron_table) != 1:
            print('Likely Problem with coronagraphic img satellite photometry')

        if len(direct_table) != 1:
            print('Likely Problem with direct img satellite photometry')

    else:
        raise TypeError('Invalid reference for apodizer status passed. Expected cnt2_apodizer or no_apodizer.')

    # Add filter info to photometry tables
    coron_table['color_filter'] = color_filter_coron
    coron_table['nd_filter'] = nd_filter_coron
    direct_table['color_filter'] = color_filter_dir
    direct_table['nd_filter'] = nd_filter_dir

    # Extract count rates
    coron_countrate = coron_table['aperture_sum'][0]
    direct_countrate = direct_table['aperture_sum'][0]

    # Calculate flux normalization factor
    factor = coron_countrate / direct_countrate  # type: float

    return direct_table, coron_table, factor
