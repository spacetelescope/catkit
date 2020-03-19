import os

from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from matplotlib.colors import LogNorm
import matplotlib.pyplot as plt
import numpy as np
from photutils import aperture_photometry
from photutils import CircularAperture
from photutils import DAOStarFinder


def satellite_photometry(data, im_spec, output_path='', rad=30, sigma=3.0, fwhm=35., save_fig=True, zoom_in=False):
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
    mean, median, std = sigma_clipped_stats(data, sigma=sigma)
    daofind = DAOStarFinder(fwhm=fwhm, threshold=7.*std)

    # Mask out all sources except top source - this region is for the 712 x 712 px HiCAT image
    mask = np.zeros(data.shape, dtype=bool)
    mask[570:712, 0:300] = True
    mask[0:570, 0:712] = True
    mask[570:712, 400:712] = True

    sources = daofind(data, mask=mask)
    positions = np.transpose((sources['xcentroid'], sources['ycentroid']))
    apertures = CircularAperture(positions, r=rad)

    phot_table = aperture_photometry(data, apertures)

    if save_fig:
        fig = plt.figure(figsize=(5, 5))

        plt.imshow(data, norm=LogNorm())
        plt.colorbar()
        if zoom_in:
            plt.ylim(sources['ycentroid'] - 100, 712)
            plt.xlim(sources['xcentroid'] - 100, sources['xcentroid'] + 100)

        apertures.plot(color='red', lw=1.5, alpha=1)
        fig.savefig(os.path.join(output_path, 'photometry-{}.pdf'.format(im_spec)), dpi=300, bbox_inches='tight')
        plt.close(fig)

    return phot_table


def get_normalization_factor(coron_data, direct_data, out_path):
    """
    Calculate flux normalization factor for direct and coron data.
    :param coron_data: tuple or string, (img, header) Pass a tuple of the coron img and header; or filepath to image.
    :param direct_data: tuple or string, (img, header) Pass a tuple of the direct img and header; or filepath to image.
    :param out_path: string, path to save outputs to
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
    coron_table = satellite_photometry(data=coron_img, im_spec='coron-{}-{}'.format(nd_filter_coron, color_filter_coron), output_path=out_path)
    direct_table = satellite_photometry(data=direct_img, im_spec='direct-{}-{}'.format(nd_filter_dir, color_filter_dir), output_path=out_path)

    if len(coron_table) != 1:
        print('Likely Problem with coronagraphic img photometry')

    if len(direct_table) != 1:
        print('Likely Problem with direct img photometry')

    # Add filter info to photometry tables
    coron_table['color_filter'] = color_filter_coron
    coron_table['nd_filter'] = nd_filter_coron
    direct_table['color_filter'] = color_filter_dir
    direct_table['nd_filter'] = nd_filter_dir

    # Calculate count rates
    coron_ap_sum = coron_table['aperture_sum'][0]
    coron_exptime = coron_header['EXP_TIME']
    coron_countrate = coron_ap_sum / coron_exptime

    direct_ap_sum = direct_table['aperture_sum'][0]
    direct_exptime = direct_header['EXP_TIME']
    direct_countrate = direct_ap_sum / direct_exptime

    # Calculate flux normalization factor
    factor = coron_countrate / direct_countrate  # type: float

    return direct_table, coron_table, factor
