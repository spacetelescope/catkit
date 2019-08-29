#file_name: AutofocusMTF.py
# author: hkurtz
# Python version of the hicat Mathematica notebook auto_focus.wl
# It is an automatized way to find the best focus position for the camera.
# Includes data reduction.
# created: 07/25/2019

import numpy as np
import matplotlib.pyplot as plt
from astropy.io import fits
from glob import glob
import os

#import util_jost as util


#if __name__ == "__main__":
def auto_focus(filePath, positions, threshold): 

    print('Starting autofocus analysis')
    """
    # Input parameters
    filePath = the path the the data taken
    positions = list of observed positions
    threshold = 100 

    #"""

    # Check how many calibrated images there are
    im_list = glob(os.path.join(filePath, '*_cal.fits*'))
    hdr = fits.getheader(im_list[0], 0)
    im_size = hdr['NAXIS1']
    numer_positions = len(positions)/2
    images = np.zeros((len(im_list), im_size, im_size))

    # Import calibrated images
    for i,file in enumerate(im_list):
        images[i] = fits.getdata(file)

    # Calculate the modulation transfer functions (MTF) and normalize them by their peaks
    OTF = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(images)))
    MTF = np.abs(OTF)
    for i in range(MTF.shape[0]):
        MTF[i] /= np.max(MTF[i])

    # Define MTF support on image that is supposed to be best focus
    central_size = int(im_size/8)
    bg_zone = MTF[int(numer_positions), 1:central_size, 1:central_size]   # Picking the central picture as reference
    noise = np.std(bg_zone)

    mask = np.ones_like(MTF[int(numer_positions)])
    bkgr = np.where(MTF[int(numer_positions)] < (threshold*noise))
    mask[bkgr] = 0

    # Calculate sum of MTF. It gets smaller when we move away from best focus
    values_MTF = []
    for i in range(MTF.shape[0]):
        values_MTF.append(np.sum(MTF[i]*mask))

    # Create motor position values and fit a 2. order curve to data
    parab = np.polyfit(positions, values_MTF, 2)
    fit = np.poly1d(parab)
    fit_x = np.linspace(positions[0], positions[-1], 50)# this is for plotting at fine samplings

    fit_data = fit(fit_x)

    # Find ideal focus
    foc_index = np.where(fit_data == np.max(fit_data))
    foc_ideal = np.float(fit_x[foc_index][0])   # [0] because the output is an array
    best_foc = np.round(foc_ideal, 2)

    print('Best focus is at ' + str(best_foc) + 'mm')

    # Plot focus fit
    plt.scatter(positions, values_MTF, c='r')
    plt.plot(fit_x, fit_data)
    plt.title('HICAT autofocus ' + ' @ ' + str(best_foc) + 'mm')
    plt.xlabel('Camera position [mm]')
    plt.ylabel('MTF sum [counts]')
    plt.savefig(os.path.join(filePath, 'autofocus_results.pdf'))
    plt.show()
