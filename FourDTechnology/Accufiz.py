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

from ...interfaces.FizeauInterferometer import FizeauInterferometer
from ...config import CONFIG_INI
from ... import util


class Accufiz(FizeauInterferometer):

    def initialize(self, mask="dm2_detector.mask", *args, **kwargs):
        """Opens connection with interferometer and returns the camera manufacturer specific object."""
        orig = time.time()
        ip = CONFIG_INI.get(self.config_id, "ip")
        timeout = CONFIG_INI.getint(self.config_id, "timeout")

        # Set the 4D timeout.
        set_timeout_string = "http://{}/WebService4D/WebService4D.asmx/SetTimeout?timeOut={}".format(ip, timeout)
        requests.get(set_timeout_string)

        # Set the Mask.
        filemask = self.__get_mask_path(mask)
        typeofmask = "Detector"
        parammask = {"maskType": typeofmask, "fileName": filemask}
        set_mask_string = "http://{}/WebService4D/WebService4D.asmx/SetMask".format(ip)
        resmask = requests.get(set_mask_string, params=parammask)

    def close(self):
        """Close interferometer connection?"""

    def take_measurement(self,
                         num_frames=2,
                         path=None,
                         filename=None):

        if path is None:
            central_store_path = CONFIG_INI.get("optics_lab", "data_path")
            path = util.create_data_path(initial_path=central_store_path, suffix="4d")

        if filename is None:
            filename = "4d_measurement"

        """Takes exposures and should be able to save fits and simply return the image data."""
        ip = CONFIG_INI.get(self.config_id, "ip")
        parammeas = {"count": int(num_frames)}

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
                return self.__convert_h5_to_fits(path, pathfile)
            else:
                print("FAIL IN SAVING MEASUREMENT " + pathfile + ".h5")
        else:
            print("FAIL IN MEASUREMENT " + pathfile + ".h5")

    @staticmethod
    def __get_mask_path(mask):
        script_dir = os.path.dirname(__file__)
        return os.path.join(script_dir, mask)

    @staticmethod
    def __convert_h5_to_fits(path, file):
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

        # Convert waves to nanometers (wavelength of 632.8).
        image = image * 632.8

        fits.PrimaryHDU(image).writeto(pathdifits, overwrite=True)
        return pathdifits

    @staticmethod
    def change_permissions_windows(path):
        import win32security
        import ntsecuritycon as con
        import os
        import pdb
        userx, domain, type = win32security.LookupAccountName("", "Everyone")
        for dirpath, dirnames, filenames in os.walk(path):
            for FILENAME in filenames:
                sd = win32security.GetFileSecurity(path + '\\' + FILENAME, win32security.DACL_SECURITY_INFORMATION)
                dacl = sd.GetSecurityDescriptorDacl()  # instead of dacl = win32security.ACL()
                dacl.AddAccessAllowedAce(win32security.ACL_REVISION, con.FILE_ALL_ACCESS, userx)
                sd.SetSecurityDescriptorDacl(1, dacl, 0)
                win32security.SetFileSecurity(path + '\\' + FILENAME, win32security.DACL_SECURITY_INFORMATION, sd)

