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
def auto_focus(filePath, start_pos, positions, incr, im_size, threshold, im_name):#   dataDir, 

    print('Starting autofocus analysis')
    """
    # Input parameters
    positions = 20 is this the number of positions? Is that equal to the number of exposures?
    incr = 0.05
    cam_z = 45.1
    start_pos = cam_z + positions*incr
    im_size = 1024
    threshold = 100 ##What is this the threshold of? Where does it come from? Does it change?
    dataDir = '11_2018-2-16'
    filePath = '../data/setup/autofocus'
    im_name = 'find_focus_'
    #"""

    # Check how many calibrated images there are
    im_list = glob(os.path.join(filePath, '*_cal.fits*'))
    images = np.zeros((len(im_list), im_size, im_size))

    # Import calibrated images
    for i in range(len(im_list)):
        pos_now = start_pos - i*incr
        filename = os.path.join(filePath, im_name + str(i) + '_' + "%.2f" % pos_now + 'mm_cal.fits')
        images[i] = fits.getdata(filename)

    # Calculate the modulation transfer functions (MTF) and normalize them by their peaks
    OTF = util.FFT(images)
    MTF = np.abs(OTF)
    for i in range(MTF.shape[0]):
        MTF[i] /= np.max(MTF[i])

    # Define MTF support on image that is supposed to be best focus
    bg_zone = MTF[positions, 1:im_size/8, 1:im_size/8]   # Picking the central picture as reference
    med = np.median(bg_zone)
    noise = np.std(bg_zone)

    mask = np.ones_like(MTF[positions])
    bkgr = np.where(MTF[positions] < (threshold*noise))
    mask[bkgr] = 0

    # Calculate sum of MTF. It gets smaller when we move away from best focus
    values_MTF = []
    for i in range(MTF.shape[0]):
        values_MTF.append(np.sum(MTF[i]*mask))

    # Create motor position values and fit a 2. order curve to data
    motors_pos = np.arange(start_pos, start_pos-2*positions*incr-incr+0.005, -incr)   # '+0.005' is included because I am having problems with np.arange stopping at the right number
    parab = np.polyfit(motors_pos, values_MTF, 2)
    fit = np.poly1d(parab)
    fit_x = np.linspace(start_pos, start_pos-2*positions*incr-incr, 50)

    fit_data = fit(fit_x)

    # Find ideal focus
    foc_index = np.where(fit(fit_x) == np.max(fit(fit_x)))
    foc_ideal = np.float(fit_x[foc_index][0])   # [0] because the output is an array
    best_foc = np.round(foc_ideal, 2)

    print('Best focus is at ' + str(best_foc) + 'mm')

    # Plot focus fit
    plt.scatter(motors_pos, values_MTF, c='r')
    plt.plot(fit_x, fit_data)
    plt.title('JOST autofocus ' + ' @ ' + str(best_foc) + 'mm')
    plt.xlabel('Camera position [mm]')
    plt.ylabel('MTF sum [counts]')
    plt.savefig(os.path.join(filePath, 'autofocus_results.pdf'))







































