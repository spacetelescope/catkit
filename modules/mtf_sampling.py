# module for sampling determination
"""
Determine the sampling of an image.
Author: Heather Olszewski
Created: 11/09/2018
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
from scipy.optimize import curve_fit

from catkit.hardware.boston.commands import flat_command
import hicat.util
from hicat.hardware import testbed
from catkit.catkit_types import *
from hicat.config import CONFIG_INI


def collect_final_images(path):
	results = [y for x in os.walk(path) for y in glob(os.path.join(x[0], "*_cal.fits"))]
	for img in results:
		copyfile(img, os.path.join(path, os.path.basename(img)))

def otf(nu, nuc):
	#nu is the fequency and nuc is te cut off frequesncy. I'm not sure where to get this info
	#nuc = 2.   # I want a single variable function so I am hacking this. We never change it anyway.
	otf_analytical = (2*np.pi) * (np.arccos(np.abs(nu/nuc)) - np.abs(nu/nuc) * np.sqrt(1 - (nu/nuc)**2))
	return otf_analytical


def otf_analytical_fit(cutoff_eq):
	px_marg_err = 3.    # the margin around cutoff_eq (either side) we want to fit
	px_step = 0.05        # steps for the fit
	
	# Create an array for the frequency region we want to fit
	fit_array = np.arange(cutoff_eq-px_marg_err, cutoff_eq+px_marg_err, px_step)
	
	# Make a least-squares fit
	one, two = curve_fit(otf, mask, mtf_masked)
	return one, two


def mtf_sampling(path,threshold):

	#im_path = 
	#threshold = 80.0

	# Import the image
	img = collect_final_images(path)
	psf = fits.getdata(img[0])
	# Get image size
	imsize = psf.shape[1]
	# Check where the PSF maximum ist
	psfmax = np.max(psf)
	posy, posx = np.where(psf == np.max(psf))
	posy = int(np.median(posy))
	posx = int(np.median(posx))

	# Calculate the OTF
	otf = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(psf)))
	# Calculate the MTF
	mtf = np.abs(otf)
	# Normalize the MTF to 1
	mtfmax = np.max(mtf)
	mtf = mtf / mtfmax

	#get image background

	# Display the MTF (absolute value of the OTF)
	plt.imshow(mtf)
	plt.title('Modulation transfer function (MTF)')
	plt.show()

	bg_zone = mtf[1:int(imsize/8), 1:int(imsize/8)]   # Picking the central picture as reference
	med = np.median(bg_zone)
	noise = np.std(bg_zone)
	
	
	mask = np.ones_like(mtf)
	bkgr = np.where(mtf < (med + threshold*noise))
	mask[bkgr] = 0
	
	mtf_masked = mtf*mask

	# Read out the area of the support we created, in pixels
	area = np.count_nonzero(mtf_masked)
	print('Support area in pixels:', area)
	
	# Calculate the radius of a circle with an equivalent area
	cutoff_eq = np.sqrt(area/np.pi)
	print('Cutoff frequency:', cutoff_eq)
	

	# Calculate your sampling
	sampling = float(imsize) / float(cutoff_eq)

	#this section does the analytical fitting. It still needs work IDK nu, not sure the otf_analytical_fit will work or the output.
	otf_analytical = otf(nu, cutoff_eq)
	one, two = otf_analytical_fit(cutoff_eq)
	otf_min = np.min(one, two)

	lam_d_wo_defocus = float(imsize) / float(otf_min)


	#print('The sampling for image "' + filename + '" is: ' + str(sampling))


	## Get the azimuthal average of radial cuts
	#radial_cuts = util.unwrap_img(mtf, (posx, posy), Ncuts=50)
	#radial_avg = np.mean(radial_cuts, axis=0)

	#plt.plot(radial_avg)
	#plt.title('Azimuthal average of radial cuts of MTF')
	#plt.show()

	## From the plot, determine an upper and lower limit in between which the MTF is 0
	#lower = 730
	#upper = 750

	## Get the position of the local minimum in this range
	#mtf_min = np.where((radial_avg == np.min(radial_avg[lower:upper])))[0]

	# Calculate your sampling
	#sampling = float(imsize) / float(mtf_min)
	#print('The sampling for image "{}" is: {}'.format(filename, sampling))

	return(ps_wo_focus, ps_w_focus, focus)
