from shutil import copyfile

import logging
import os
from glob import glob

from astropy.io import fits
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.colors import LogNorm
import numpy as np

from catkit.hardware.boston.commands import flat_command
import hicat.util
from hicat.hardware import testbed
from catkit.catkit_types import *
from hicat.config import CONFIG_INI


def take_auto_focus_data(bias,
                         flat_map,
                         exposure_time,
                         num_exposures,
                         position_list,
                         path,
                         camera_type,
                         **kwargs):
    log = logging.getLogger(__name__)
    # Wait to set the path until the experiment starts (rather than the constructor)
    if path is None:
        path = hicat.util.create_data_path(suffix="focus")
        hicat.util.setup_hicat_logging(path, "focus")


    camera_motor = testbed.get_camera_motor_name(camera_type)

    with testbed.laser_source() as laser:
        direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
        laser.set_current(direct_laser_current)

        with testbed.motor_controller():
            # Initialize motors.
            log.info("Initialized motors for Auto Focus once, and will now only move the camera motor.")

        with testbed.dm_controller() as dm:
            dm_command_object = flat_command(bias=bias, flat_map=flat_map)
            dm_command_object_2 = flat_command(bias=bias, flat_map=flat_map, dm_num=2)
            dm.apply_shape_to_both(dm_command_object, dm_command_object_2)

            for i, position in enumerate(position_list):
                with testbed.motor_controller(initialize_to_nominal=False) as mc:
                    mc.absolute_move(camera_motor, position)
                filename = "focus_" + str(int(position * 1000))
                metadata = MetaDataEntry("Camera Position", "CAM_POS", position * 1000, "Position * 1000")
                testbed.run_hicat_imaging(exposure_time, num_exposures, FpmPosition.direct, path=path,
                                          filename=filename,
                                          exposure_set_name="motor_" + str(int(position * 1000)),
                                          extra_metadata=metadata,
                                          init_motors=False,
                                          camera_type=camera_type,
                                          **kwargs)
    return path


def collect_final_images(path):
    results = [y for x in os.walk(path) for y in glob(os.path.join(x[0], "*_cal.fits"))]
    for img in results:
        copyfile(img, os.path.join(path, os.path.basename(img)))


def auto_focus_mtf(filePath, threshold):
    """
    Perform MTF analysis to find best focus position for imaging camera.
    :param filePath: path to autofocus data
    :param threshold: threshold for background
    """

    print('Starting autofocus analysis')

    # Create directory for diagnostics
    mtf_dir = 'mtf_diagnostics'
    os.makedirs(os.path.join(filePath, mtf_dir), exist_ok=True)

    # Read calibrated images
    im_list = glob(os.path.join(filePath, '*_cal.fits*'))

    # Determine at what camera positions the images were taken, in order they were read in
    positions = []
    for i in range(len(im_list)):
        hdr = fits.getheader(im_list[i], 0)
        positions.append(hdr['CAM_POS'] / 1e3)  # transform to mm
    positions = np.array(positions)

    # Set up array of all PSF images
    hdr = fits.getheader(im_list[0], 0)
    im_size = hdr['NAXIS1']
    number_positions = len(positions)/2
    images = np.zeros((len(im_list), im_size, im_size))

    # Import calibrated images
    for i, file in enumerate(im_list):
        images[i] = fits.getdata(file)

    # Calculate the modulation transfer functions (MTF) and normalize them by their peaks
    OTF = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(images)))
    MTF = np.abs(OTF)
    for i in range(MTF.shape[0]):
        MTF[i] /= np.max(MTF[i])

        # Save MTFs as fits
        hicat.util.write_fits(MTF[i], os.path.join(filePath, mtf_dir, 'mtf_' + str(positions[i]) + '.fits'))

    # Define MTF support on image that is supposed to be best focus
    central_size = int(im_size/8)
    bg_zone = MTF[int(number_positions), 1:central_size, 1:central_size]   # Picking the central picture as reference
    noise = np.std(bg_zone)

    mask = np.ones_like(MTF[int(number_positions)])
    bkgr = np.where(MTF[int(number_positions)] < (threshold*noise))
    mask[bkgr] = 0

    # Save used background area
    rect = Rectangle((1, 1), central_size, central_size, linewidth=1, edgecolor='r', facecolor='none')
    plt.clf()
    plt.imshow(MTF[0])
    plt.gca().add_patch(rect)
    plt.savefig(os.path.join(filePath, mtf_dir, 'background_area.pdf'))

    # Save MTF support
    plt.clf()
    plt.imshow(mask)
    plt.savefig(os.path.join(filePath, mtf_dir, 'mtf_support.pdf'))

    # Calculate sum of MTF. It gets smaller when we move away from best focus
    values_MTF = []
    for i in range(MTF.shape[0]):
        values_MTF.append(np.sum(MTF[i]*mask))

        # create MTF plot and save as pdf
        plt.clf()
        plt.imshow(MTF[i] * mask, norm=LogNorm())
        plt.title(str(positions[i]) + ' mm')
        plt.savefig(os.path.join(filePath, mtf_dir, 'mtf_' + str(positions[i]) + '.pdf'))

    # Create motor position values and fit a 2. order curve to data
    parab = np.polyfit(positions, values_MTF, 2)
    fit = np.poly1d(parab)
    fit_x = np.linspace(np.min(positions), np.max(positions), 50)   # this is for plotting at fine samplings

    fit_data = fit(fit_x)

    # Find ideal focus
    foc_index = np.where(fit_data == np.max(fit_data))
    foc_ideal = np.float(fit_x[foc_index][0])   # [0] because the output is an array
    best_foc = np.round(foc_ideal, 2)

    print('Best focus is at ' + str(best_foc) + 'mm')

    # Plot focus fit
    plt.clf()
    plt.scatter(positions, values_MTF, c='r', label='data points')
    plt.plot(fit_x, fit_data, label='model fit')
    plt.title('HICAT autofocus ' + ' @ ' + str(best_foc) + 'mm')
    plt.xlabel('Camera position [mm]')
    plt.ylabel('MTF sum [counts]')
    plt.legend()
    plt.savefig(os.path.join(filePath, 'autofocus_results.pdf'))
    plt.show()
