"""
module for pixel sampling determination
"""

from shutil import copyfile

import logging
import os
from glob import glob

from astropy.io import fits
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.colors import LogNorm
import numpy as np
from scipy.ndimage.interpolation import affine_transform


def collect_final_images(path):
	results = glob(os.path.join(path, "*_cal.fits"))
	im = str(results[0])
	return im


def mtf_sampling(path,threshold):
	mtf_dir = 'mtf_diagnostics'
	os.makedirs(os.path.join(path, mtf_dir), exist_ok=True)

	im_path = collect_final_images(path)
	psf = fits.getdata(im_path)
	imsize = psf.shape[1]

	# Calculate the OTF
	otf = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(psf)))
	mtf = np.abs(otf)
	mtfmax = np.max(mtf)
	mtf = mtf / mtfmax

	plt.clf()
	plt.imshow(mtf)
	plt.title('Modulation transfer function (MTF)')
	plt.savefig(os.path.join(path, mtf_dir, 'MTF.pdf'))

	bg_zone = mtf[1:int(imsize/8), 1:int(imsize/8)]
	med = np.median(bg_zone)
	noise = np.std(bg_zone)	
	mask = np.ones_like(mtf)
	bkgr = np.where(mtf < (med + threshold*noise))
	mask[bkgr] = 0

	plt.clf()
	plt.imshow(mask)
	plt.savefig(os.path.join(path, mtf_dir, 'mtf_support.pdf'))	
	mtf_masked = mtf*mask
	plt.clf()
	plt.imshow(mtf_masked, norm=LogNorm())
	plt.title('Modulation transfer function (MTF) Masked')
	plt.savefig(os.path.join(path, mtf_dir, 'mtf_masked.pdf'))

	area = np.count_nonzero(mtf_masked)
	cutoff_eq = np.sqrt(area/np.pi)
	sampling = float(imsize) / float(cutoff_eq)

	return(sampling)


