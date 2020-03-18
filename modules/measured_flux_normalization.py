import os

from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.visualization import ZScaleInterval
import matplotlib.pyplot as plt
import numpy as np
from photutils import aperture_photometry
from photutils import CircularAperture
from photutils import DAOStarFinder

zscale = ZScaleInterval(contrast=0.10).get_limits


def satellite_photometry(data, im_type, rad=30, sigma=3.0, fwhm=35., save_fig=True, zoom_in=False):
    """
    Performs source detection and extraction on 'data' within spatial limits.
    :param data: array, image to analyze
    :param im_type: string, 'direct' or 'coron' (only used to name plot)
    :param rad: int, radius of photometry aperture
    :param sigma: float, number of stddevs for clipping limit
    :param fwhm: float, full-width-half-max of source
    :param save_fig: bool, toggle to save figures
    :param zoom_in: bool, saves a cropped image with the aperture in more detail
    :return:
    """
    mean, median, std = sigma_clipped_stats(data, sigma=sigma)
    daofind = DAOStarFinder(fwhm=fwhm, threshold=7. * std)

    # Mask out all sources except top source - this region is for the 712 x 712 px HiCAT image
    mask = np.zeros(data.shape, dtype=bool)
    mask[570:712, 0:300] = True
    mask[0:570, 0:712] = True
    mask[570:712, 400:712] = True

    sources = daofind(data - median, mask=mask)
    positions = np.transpose((sources['xcentroid'], sources['ycentroid']))
    apertures = CircularAperture(positions, r=rad)

    phot_table = aperture_photometry(data, apertures)

    if save_fig:
        fig = plt.figure(figsize=(5, 5))
        vmin, vmax = zscale(data)

        plt.imshow(data, vmin=vmin, vmax=vmax, origin='lower')
        plt.colorbar()
        if zoom_in:
            plt.ylim(sources['ycentroid'] - 100, 712)
            plt.xlim(sources['xcentroid'] - 100, sources['xcentroid'] + 100)

        apertures.plot(color='red', lw=1.5, alpha=1)
        fig.savefig('diagnostic_{}_photometry.png'.format(im_type), dpi=300, bbox_inches='tight')
        plt.close(fig)

    return phot_table


def get_normalization_factor(coron_data, direct_data):
    """
    Calculate flux normalization factor for direct vs. coron data.
    :param coron_data: tuple or string, (img, header) Pass a tuple of the coron img and header; or filepath to image.
    :param direct_data: tuple or string, (img, header) Pass a tuple of the direct img and header; or filepath to image.
    """
    # Unpack a Tuple header
    coron_header = coron_data[1]
    coron_img = coron_data[0]
    direct_header = direct_data[1]
    direct_img = direct_data[0]

    # If a filepath is passed
    if type(coron_data) == str:
        if os.path.exists(coron_data):
            coron_header = fits.getheader(coron_data)
            coron_img = fits.getdata(coron_data)

    if type(direct_data) == str:
        if os.path.exists(direct_data):
            direct_header = fits.getheader(direct_data)
            direct_img = fits.getdata(direct_data)

    coron_type = coron_header['FILENAME'].split('_')[0]
    direct_type = coron_header['FILENAME'].split('_')[0]

    coron_filter = coron_header['FILTERS'].split(',')[0]
    direct_filter = coron_header['FILTERS'].split(',')[0]

    coron_table = satellite_photometry(coron_img, save_fig=True, im_type=coron_type, zoom_in=False)
    direct_table = satellite_photometry(direct_img, save_fig=True, im_type=direct_type, zoom_in=False)

    if len(coron_table) != 1:
        print('Likely Problem with Coronagraphic img Photometry')

    if len(direct_table) != 1:
        print('Likely Problem with Direct img Photometry')

    coron_ap_sum = coron_table['aperture_sum'][0]
    coron_exptime = coron_header['EXP_TIME']
    coron_countrate = coron_ap_sum / coron_exptime

    direct_ap_sum = direct_table['aperture_sum'][0]
    direct_exptime = direct_header['EXP_TIME']
    direct_countrate = direct_ap_sum / direct_exptime

    factor = coron_countrate / direct_countrate  # type: float
    return factor
