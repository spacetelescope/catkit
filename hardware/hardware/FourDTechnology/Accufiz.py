from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import h5py
import time
import requests
import os
import math
import numpy as np
from astropy.io import fits
from scipy import ndimage
from glob import glob

from hicat.interfaces.FizeauInterferometer import FizeauInterferometer
from hicat.config import CONFIG_INI
from hicat import util


class Accufiz(FizeauInterferometer):

    def initialize(self, mask="dm2_detector.mask", *args, **kwargs):
        """Opens connection with interferometer and returns the camera manufacturer specific object."""
        orig = time.time()
        ip = CONFIG_INI.get(self.config_id, "ip")
        timeout = CONFIG_INI.getint(self.config_id, "timeout")

        # Set the 4D timeout.
        set_timeout_string = "http://{}/WebService4D/WebService4D.asmx/SetTimeout?timeOut={}".format(ip, timeout)
        requests.get(set_timeout_string)

        # Set the Mask. This mask has to be local to the 4D computer in this directory.
        # filemask = os.path.join("c:\\4Sight_masks", mask)
        # typeofmask = "Detector"
        # parammask = {"maskType": typeofmask, "fileName": filemask}
        # set_mask_string = "http://{}/WebService4D/WebService4D.asmx/SetMask".format(ip)
        # resmask = requests.post(set_mask_string, data=parammask)

    def close(self):
        """Close interferometer connection?"""

    def take_measurement(self,
                         num_frames=2,
                         path=None,
                         filename=None,
                         rotate=0,
                         fliplr=False,
                         exposure_set=""):

        if path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "data_path")
            path = util.create_data_path(initial_path=central_store_path, suffix="4d")

        if filename is None:
            filename = "4d_measurement"

        """Takes exposures and should be able to save fits and simply return the image data."""
        ip = CONFIG_INI.get(self.config_id, "ip")
        parammeas = {"count": int(num_frames)}

        try_counter = 0
        tries = 10
        while try_counter < tries:
            measres = requests.post('http://{}/WebService4D/WebService4D.asmx/AverageMeasure'.format(ip), data=parammeas)

            pathfile = os.path.join(path, filename)

            #  This line is here because when sent through webservice slashes tend
            #  to disappear. If we sent in parameter a path with only one slash,
            #  they disappear
            pathfile = pathfile.replace('\\',
                                        '/')

            pathfile = pathfile.replace('/',
                                        '\\\\')

            paramsave = {"fileName": pathfile}

            if 'success' in measres.text:
                if not os.path.exists(path):
                    os.makedirs(path)
                r = requests.post("http://{}/WebService4D/WebService4D.asmx/SaveMeasurement".format(ip), data=paramsave)
                time.sleep(1)
                if glob(pathfile + '.h5'):
                    print('SUCCESS IN SAVING ' + pathfile)
                    return self.__convert_h5_to_fits(path, pathfile, rotate, fliplr)
                else:
                    try_counter += 1
                    print("FAIL IN SAVING MEASUREMENT " + pathfile + ".h5")
                    if try_counter < tries:
                        print("Trying again..")
            else:
                try_counter += 1
                print("FAIL IN MEASUREMENT " + pathfile + ".h5")
                print(measres.text)
                if try_counter < tries:
                    print("Trying again..")


    @staticmethod
    def __get_mask_path(mask):
        script_dir = os.path.dirname(__file__)
        return os.path.join(script_dir, mask)

    @staticmethod
    def __convert_h5_to_fits(path, file, rotate, fliplr):
        os.chdir(path)

        file = file if file.endswith(".h5") else file + ".h5"
        pathfile = file
        pathdifits = file[:-3] + '.fits'

        maskinh5 = np.array(h5py.File(pathfile, 'r').get('measurement0').get('Detectormask'))
        image0 = np.array(h5py.File(pathfile, 'r').get('measurement0').get('genraw').get('data')) * maskinh5

        fits.PrimaryHDU(maskinh5).writeto(pathdifits, overwrite=True)

        radiusmask = np.int(np.sqrt(np.sum(maskinh5) / math.pi))
        center = ndimage.measurements.center_of_mass(maskinh5)

        image = np.clip(image0, -10, +10)[np.int(center[0]) - radiusmask:np.int(center[0]) + radiusmask - 1,
                np.int(center[1]) - radiusmask: np.int(center[1]) + radiusmask - 1]

        # Apply the rotation and flips.
        image = util.rotate_and_flip_image(image, rotate, fliplr)

        # Convert waves to nanometers (wavelength of 632.8).
        image = image * 632.8

        fits.PrimaryHDU(image).writeto(pathdifits, overwrite=True)
        return pathdifits
