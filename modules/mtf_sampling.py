"""
module for pixel sampling determination
"""
import os

from astropy.io import fits
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np
import hicat.util


def mtf_sampling(dirpath, im_path, threshold):
	"""
	Calculate the MTF pixel sampling using the equivalent area method.
	    Inputs
	        dirpath: string, path to the to the directory for the output MTF data
	        im_path: string, path to the focused input image
	        threshold: int, the background threshold used to calculate the MTF  support
	    Output
	        sampling: float, the MTF sampling in pixels per lambda/D
	"""
	mtf_dir = hicat.util.create_data_path(dirpath, suffix='mtf_diagnostics')
	os.makedirs(mtf_dir, exist_ok=True)

	psf = fits.getdata(im_path)
	full_imsize = psf.shape[1]
	psf_sub = psf[int(full_imsize/4):int(full_imsize/1.4), int(full_imsize/4):int(full_imsize/1.4)]
	imsize = psf_sub.shape[1]

	# Save cropped image to diagnostics
	hicat.util.write_fits(psf_sub, os.path.join(mtf_dir, 'cropped_image.fits'))

	# Calculate the OTF
	otf = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(psf_sub)))
	mtf = np.abs(otf)
	mtfmax = np.max(mtf)
	mtf = mtf / mtfmax

	plt.clf()
	plt.imshow(mtf)
	plt.title('Modulation transfer function (MTF)')
	plt.savefig(os.path.join(mtf_dir, 'MTF.pdf'))

	bg_zone = mtf[1:int(imsize/8), 1:int(imsize/8)]
	med = np.median(bg_zone)
	noise = np.std(bg_zone)	
	mask = np.ones_like(mtf)
	bkgr = np.where(mtf < (med + threshold*noise))
	mask[bkgr] = 0

	plt.clf()
	plt.imshow(mask)
	plt.savefig(os.path.join(mtf_dir, 'mtf_support.pdf'))
	mtf_masked = mtf * mask
	plt.clf()
	plt.imshow(mtf_masked, norm=LogNorm())
	plt.title('Modulation transfer function (MTF) Masked')
	plt.savefig(os.path.join(mtf_dir, 'mtf_masked.pdf'))

	area = np.count_nonzero(mtf_masked)
	cutoff_eq = np.sqrt(area/np.pi)
	sampling = float(imsize) / float(cutoff_eq)

	with open(os.path.join(mtf_dir, 'sampling_params.txt'), 'w') as f:
		f.write('sampling: {}\n'.format(sampling))
		f.write('threshold: {}'.format(threshold))

	return sampling