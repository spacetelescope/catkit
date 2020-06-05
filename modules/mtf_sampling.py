"""
module for pixel sampling determination
"""
import os

import sys
import subprocess
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
	psf_sub = psf[int(full_imsize/4):int(3*full_imsize/4), int(full_imsize/4):int(3*full_imsize/4)]
	imsize = psf_sub.shape[1]

	# Save cropped image to diagnostics
	hicat.util.write_fits(psf_sub, os.path.join(mtf_dir, 'cropped_image.fits'))

	# Calculate the OTF
	otf = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(psf_sub)))
	mtf = np.abs(otf)
	mtfmax = np.max(mtf)
	mtf = mtf / mtfmax

	vmax = mtf.max()
	vmin = vmax/1e6
	norm = LogNorm(vmin=vmin, vmax=vmax)

	fig, axes = plt.subplots(nrows=1, ncols=3, figsize=(12,5))
	axes[0].imshow(mtf, norm=norm)
	axes[0].set_title('Modulation transfer function (MTF)')

	bg_zone = mtf[1:int(imsize/8), 1:int(imsize/8)]
	med = np.median(bg_zone)
	noise = np.std(bg_zone)	
	mask = np.ones_like(mtf)
	bkgr = np.where(mtf < (med + threshold*noise))

	axes[0].set_xlabel(f"Estimated background noise std dev: {noise:.4g}" )
	mask[bkgr] = 0

	# draw contour in alternating colors to ensure reasonable contrast
	axes[0].contour(mask, alpha=0.5, colors=['orange'], linestyles='dotted', linewidths=[0.75])

	axes[1].imshow(mask)
	axes[1].set_title("MTF support")
	axes[1].set_xlabel(f"with threshold = {threshold}")
	#axes[1].savefig(os.path.join(mtf_dir, 'mtf_support.pdf'))
	mtf_masked = mtf * mask

	axes[2].imshow(mtf_masked, norm=norm)
	axes[2].set_title('Modulation transfer function (MTF) Masked')

	area = np.count_nonzero(mtf_masked)
	cutoff_eq = np.sqrt(area/np.pi)
	sampling = float(imsize) / float(cutoff_eq)

	fig.suptitle(f"MTF Measurement: {dirpath}\n\nSampling = {sampling:.4f}")

	output_pdf = os.path.join(mtf_dir, 'mtf_results.pdf')
	plt.savefig(output_pdf)

	with open(os.path.join(mtf_dir, 'sampling_params.txt'), 'w') as f:
		f.write('sampling: {}\n'.format(sampling))
		f.write('threshold: {}'.format(threshold))

	if sys.platform=='darwin':
		# for convenience, open the PDF in a viewer
		subprocess.call(['open', output_pdf])

	return sampling