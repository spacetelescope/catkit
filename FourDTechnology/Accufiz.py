from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import time
import requests
import os

from ...interfaces.FizeauInterferometer import FizeauInterferometer

from ...config import CONFIG_INI
from glob import glob


class Accufiz(FizeauInterferometer):

    def initialize(self, *args, **kwargs):
        """Opens connection with interferometer and returns the camera manufacturer specific object."""
        orig = time.time()
        ip = CONFIG_INI.get(self.config_id, "ip")
        timeout = CONFIG_INI.getint(self.config_id, "timeout")

        # Set the 4D timeout.
        set_timeout_string = "http://{}/WebService4D/WebService4D.asmx/SetTimeout?timeOut={}".format(ip, timeout)
        requests.get(set_timeout_string)

        # Set the Mask.
        filemask = self.__get_mask_path()
        typeofmask = "Detector"
        parammask = {"maskType": typeofmask, "fileName": filemask}
        set_mask_string = "http://{}/WebService4D/WebService4D.asmx/SetMask".format(ip)
        resmask = requests.get(set_mask_string, params=parammask)

    def close(self):
        """Close interferometer connection?"""

    def take_measurement(self, num_frames, path, filename, *args, **kwargs):
        orig = time.time()

        """Takes exposures and should be able to save fits and simply return the image data."""
        ip = CONFIG_INI.get(self.config_id, "ip")
        parammeas = {"count": int(num_frames)}

        measres = requests.post('http://{}/WebService4D/WebService4D.asmx/AverageMeasure'.format(ip), data=parammeas)

        pathfile = os.path.join(path, filename)  # pathdir + inputfile

        #  This line is here because when sent through webservice slashes tend
        #  to disappear. If we sent in parameter a path with only one slash,
        #  they disappear

        paramsave = {"fileName": pathfile}

        if 'success' in measres.text:
            r = requests.post("http://192.168.192.131/WebService4D/WebService4D.asmx/SaveMeasurement", data=paramsave)
            if glob(pathfile + '.h5'):
                print('SUCCESS IN SAVING ' + pathfile + '.h5 : ' + num_frames + 'frames in ' + str(time.time() - orig))
            else:
                print("FAIL IN SAVING MEASUREMENT " + pathfile + ".h5")
        else:
            print("FAIL IN MEASUREMENT " + pathfile + ".h5")

    @staticmethod
    def __get_mask_path():
        script_dir = os.path.dirname(__file__)
        return os.path.join(script_dir, "dm2_detector.mask")

