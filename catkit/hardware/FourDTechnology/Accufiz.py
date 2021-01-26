import h5py
import math
import os
import requests
import tempfile
import time
import shutil
import uuid

from astropy.io import fits
from glob import glob
import numpy as np
from scipy import ndimage

from catkit.interfaces.FizeauInterferometer import FizeauInterferometer
import catkit.util
from catkit.config import CONFIG_INI


class Accufiz(FizeauInterferometer):

    instrument_lib = requests

    def initialize(self, local_path, server_path, mask="dm2_detector.mask", post_save_sleep=1, file_mode=True):
        """

        :param local_path: str, The local path accessible from Python.
        :param server_path: str, The path accessible from the 4D server.
        :param mask: str, ?
        :param post_save_sleep: int, float, Seconds to sleep between saving and checking for success.
        :param file_mode: bool, whether to save images to disk.
        """
        self.ip = CONFIG_INI.get(self.config_id, "ip")
        self.timeout = CONFIG_INI.getint(self.config_id, "timeout")
        self.html_prefix = f"http://{self.ip}/WebService4D/WebService4D.asmx"
        self.mask = mask
        self.post_save_sleep = post_save_sleep
        self.file_mode = file_mode

        self.temp_dir = tempfile.TemporaryDirectory()
        self.local_path = os.path.join(local_path, self.temp_dir.name)
        self.server_path = os.path.join(server_path, self.temp_dir.name)

    def _open(self):
        # Set the 4D timeout.
        set_timeout_string = f"{self.html_prefix}/SetTimeout?timeOut={self.timeout}"
        self.instrument_lib.get(set_timeout_string)

        # Set the Mask. This mask has to be local to the 4D computer in this directory.
        # filemask = os.path.join("c:\\4Sight_masks", self.mask)
        # typeofmask = "Detector"
        # parammask = {"maskType": typeofmask, "fileName": filemask}
        # set_mask_string = "http://{}/WebService4D/WebService4D.asmx/SetMask".format(ip)
        # resmask = requests.post(set_mask_string, data=parammask)

        return True  # We're "open".

    def _close(self):
        """Close interferometer connection?"""
        pass

    def take_measurement(self,
                         num_frames=2,
                         filepath=None,
                         rotate=0,
                         fliplr=False,
                         exposure_set=""):

        # Send request to take data.
        measurement_resp = self.instrument_lib.post(f"{self.html_prefix}/AverageMeasure", data={"count": int(num_frames)})
        if "success" not in measurement_resp.text:
            raise RuntimeError(f"{self.config_id}: Failed to take data - {measurement_resp.text}.")

        filename = str(uuid.uuid4())
        server_file_path = os.path.join(self.server_path, filename)
        local_file_path = os.path.join(self.local_path, filename)

        #  This line is here because when sent through webservice slashes tend
        #  to disappear. If we sent in parameter a path with only one slash,
        #  they disappear
        server_file_path = server_file_path.replace('\\', '/')
        server_file_path = server_file_path.replace('/', '\\\\')

        # Send request to save data.
        _resp = self.instrument_lib.post(f"{self.html_prefix}/SaveMeasurement", data={"fileName": server_file_path})
        time.sleep(self.post_save_sleep)

        if not glob(f"{local_file_path}.h5"):
            raise RunTimeException(f"{self.config_id}: Failed to save measurement data to '{local_file_path}'.")

        self.log.info(f"{self.config_id}: Succeeded to save measurement data to '{local_file_path}'")

        fits_local_file_path, fits_hdu = self.convert_h5_to_fits(local_file_path, rotate, fliplr)

        if self.file_mode:
            if not filepath:
                raise ValueError("A filepath is required to write data to disk.")
            shutil.copyfile(fits_local_file_path, filepath)

        return fits_hdu

    @staticmethod
    def __get_mask_path(mask):
        calibration_data_package = CONFIG_INI.get("optics_lab", "calibration_data_package")
        calibration_data_path = os.path.join(catkit.util.find_package_location(calibration_data_package),
                                             "hardware",
                                             "FourDTechnology")
        return os.path.join(calibration_data_path, mask)

    @staticmethod
    def convert_h5_to_fits(filepath, rotate, fliplr, wavelength=632.8):

        filepath = filepath if filepath.endswith(".h5") else f"{filepath}.h5"

        fits_filepath = f"{os.path.splitext(filepath)[0]}.fits"

        maskinh5 = np.array(h5py.File(filepath, 'r').get('measurement0').get('Detectormask'))
        image0 = np.array(h5py.File(filepath, 'r').get('measurement0').get('genraw').get('data')) * maskinh5

        fits.PrimaryHDU(maskinh5).writeto(fits_filepath, overwrite=True)

        radiusmask = np.int(np.sqrt(np.sum(maskinh5) / math.pi))
        center = ndimage.measurements.center_of_mass(maskinh5)

        image = np.clip(image0, -10, +10)[np.int(center[0]) - radiusmask:np.int(center[0]) + radiusmask - 1,
                np.int(center[1]) - radiusmask: np.int(center[1]) + radiusmask - 1]

        # Apply the rotation and flips.
        image = catkit.util.rotate_and_flip_image(image, rotate, fliplr)

        # Convert waves to nanometers.
        image = image * wavelength

        fits.PrimaryHDU(image).writeto(fits_filepath, overwrite=True)
        return fits_filepath, fits_hdu
