from catkit.catkit_types import MetaDataEntry
from catkit.interfaces.Camera import Camera
from catkit.config import CONFIG_INI
from catkit.catkit_types import units, quantity
import catkit.util
from astropy.io import fits
import numpy as np
import logging
import os
import requests
import sys

import catkit.util


# implementation of a camera to run the SBIG STX-16803 Pupil Cam and KAF-1603ME/STT-1603M small cam

class SbigCamera(Camera):
    FRAME_TYPE_DARK = 0
    FRAME_TYPE_LIGHT = 1
    FRAME_TYPE_BIAS = 2
    FRAME_TYPE_FLAT_FIELD = 3

    IMAGER_STATE_IDLE = 0
    IMAGER_STATE_EXPOSING = 2
    IMAGER_STATE_READING_OUT = 3
    IMAGER_STATE_ERROR = 5

    NO_IMAGE_AVAILABLE = 0
    IMAGE_AVAILABLE = 1

    log = logging.getLogger()

    def initialize(self, *args, **kwargs):
        """Loads the SBIG config information and verifies that the camera is idle.
           Uses the config_id to look up parameters in the config.ini"""

        # find the SBIG config information
        camera_name = CONFIG_INI.get(self.config_id, "camera_name")
        self.base_url = CONFIG_INI.get(self.config_id, "base_url")
        self.timeout = CONFIG_INI.getint(self.config_id, "timeout")
        self.min_delay = CONFIG_INI.getfloat(self.config_id, 'min_delay')

        # check the status, which should be idle
        imager_status = self.__check_imager_state()
        if imager_status > self.IMAGER_STATE_IDLE:
            # Error.  Can't start the camera or camera is already busy
            raise Exception("Camera reported incorrect state (" + str(imager_status) + ") during initialization.")

        self.imager_status = imager_status

    def close(self):
        # check status and abort any imaging in progress
        imager_status = self.__check_imager_state()
        if imager_status > self.IMAGER_STATE_IDLE:
            # work in progress, abort the exposure
            catkit.util.sleep(self.min_delay)  # limit the rate at which requests go to the camera
            r = requests.get(self.base_url + "ImagerAbortExposure.cgi")
            # no data is returned, but an http error indicates if the abort failed
            r.raise_for_status()

    def take_exposures(self, exposure_time, num_exposures,
                       file_mode=False, raw_skip=0, path=None, filename=None,
                       extra_metadata=None,
                       resume=False,
                       return_metadata=False,
                       subarray_x=None, subarray_y=None, width=None, height=None, gain=None, full_image=None,
                       bins=None):
        """
        Low level method to take exposures using an SBIG camera. By default keeps image data in memory
        :param exposure_time: Pint quantity for exposure time, otherwise in microseconds.
        :param num_exposures: Number of exposures.
        :param file_mode: If true fits file will be written to disk
        :param raw_skip: Skips x images for every one taken, when used images will be stored in memory and returned.
        :param path: Path of the directory to save fits file to, required if write_raw_fits is true.
        :param filename: Name for file, required if write_raw_fits is true.
        :param extra_metadata: Will be appended to metadata created and written to fits header.
        :param resume: If True, skips exposure if filename exists on disk already. Doesn't support data-only mode.
        :param return_metadata: If True, returns a list of meta data as a second return parameter.
        :param subarray_x: X coordinate of center pixel of the subarray.
        :param subarray_y: Y coordinate of center pixel of the subarray.
        :param width: Desired width of image.
        :param height: Desired height of image.
        :param gain: Gain is ignored for the SBIG camera; the API doesn't have a way to set gain.
        :param full_image: Boolean for whether to take a full image.
        :param bins: Integer value for number of bins.
        :return: Two parameters: Image list (numpy data or paths), Metadata list of MetaDataEntry objects.
        """

        # Convert exposure time to contain units if not already a Pint quantity.
        if type(exposure_time) is not quantity:
            exposure_time = quantity(exposure_time, units.microsecond)

        self.__setup_control_values(exposure_time, subarray_x=subarray_x, subarray_y=subarray_y, width=width,
                                    height=height, gain=gain, full_image=full_image, bins=bins)

        # Create metadata from extra_metadata input.
        meta_data = [MetaDataEntry("Exposure Time", "EXP_TIME", exposure_time.to(units.microsecond).m, "microseconds")]
        meta_data.append(MetaDataEntry("Camera", "CAMERA", self.config_id, "Camera model, correlates to entry in ini"))
        meta_data.append(MetaDataEntry("Bins", "BINS", self.bins, "Binning for camera"))
        if extra_metadata is not None:
            if isinstance(extra_metadata, list):
                meta_data.extend(extra_metadata)
            else:
                meta_data.append(extra_metadata)

        # DATA MODE: Takes images and returns data and metadata (does not write anything to disk).
        img_list = []
        if not file_mode:
            # Take exposures and add to list.
            for i in range(num_exposures):
                img = self.__capture(exposure_time)
                img_list.append(img)
            if return_metadata:
                return img_list, meta_data
            else:
                return img_list
        else:
            # Check that path and filename are specified.
            if path is None or filename is None:
                raise Exception("You need to specify path and filename when file_mode=True.")

        # FILE MODE:
        # Check for fits extension.
        if not (filename.endswith(".fit") or filename.endswith(".fits")):
            filename += ".fits"

        # Split the filename once here, code below may append _frame=xxx to basename.
        file_split = os.path.splitext(filename)
        file_root = file_split[0]
        file_ext = file_split[1]

        # Create directory if it doesn't exist.
        if not os.path.exists(path):
            os.makedirs(path)

        # Take exposures. Use Astropy to handle fits format.
        skip_counter = 0
        for i in range(num_exposures):

            # For multiple exposures append frame number to end of base file name.
            if num_exposures > 1:
                filename = file_root + "_frame" + str(i + 1) + file_ext
            full_path = os.path.join(path, filename)

            # If Resume is enabled, continue if the file already exists on disk.
            if resume and os.path.isfile(full_path):
                self.log.info("File already exists: " + full_path)
                img_list.append(full_path)
                continue

            # Take exposure.
            img = self.__capture(exposure_time)

            # Skip writing the fits files per the raw_skip value, and keep img data in memory.
            if raw_skip != 0:
                img_list.append(img)
                if skip_counter == (raw_skip + 1):
                    skip_counter = 0
                if skip_counter == 0:
                    # Write fits.
                    skip_counter += 1
                elif skip_counter > 0:
                    # Skip fits.
                    skip_counter += 1

                    continue

            # Create a PrimaryHDU object to encapsulate the data.
            hdu = fits.PrimaryHDU(img)

            # Add headers.
            hdu.header["FRAME"] = i + 1
            hdu.header["FILENAME"] = filename

            # Add testbed state metadata.
            for entry in meta_data:
                if len(entry.name_8chars) > 8:
                    self.log.warning("Fits Header Keyword: " + entry.name_8chars +
                          " is greater than 8 characters and will be truncated.")
                if len(entry.comment) > 47:
                    self.log.warning("Fits Header comment for " + entry.name_8chars +
                          " is greater than 47 characters and will be truncated.")
                hdu.header[entry.name_8chars[:8]] = (entry.value, entry.comment)

            # Create a HDUList to contain the newly created primary HDU, and write to a new file.
            fits.HDUList([hdu])
            hdu.writeto(full_path, overwrite=True)
            self.log.info("wrote " + full_path)
            if raw_skip == 0:
                img_list.append(full_path)

        # If data mode, return meta_data with data.
        if return_metadata:
            return img_list, meta_data
        else:
            return img_list

    def __setup_control_values(self, exposure_time, subarray_x=None, subarray_y=None, width=None, height=None,
                               gain=None, full_image=None, bins=None):
        """Applies control values found in the config.ini unless overrides are passed in, and does error checking.
           Makes HTTP requests to set the imager settings.  Will raise an exception for an HTTP error."""

        self.log.info("Setting up control values")
        # Load values from config.ini into variables, and override with keyword args when applicable.
        self.cooler_state = CONFIG_INI.getint(self.config_id, 'cooler_state')
        self.subarray_x = subarray_x if subarray_x is not None else CONFIG_INI.getint(self.config_id, 'subarray_x')
        self.subarray_y = subarray_y if subarray_y is not None else CONFIG_INI.getint(self.config_id, 'subarray_y')
        self.width = width if width is not None else CONFIG_INI.getint(self.config_id, 'width')
        self.height = height if height is not None else CONFIG_INI.getint(self.config_id, 'height')
        self.full_image = full_image if full_image is not None else CONFIG_INI.getboolean(self.config_id, 'full_image')
        self.bins = bins if bins is not None else CONFIG_INI.getint(self.config_id, 'bins')
        self.exposure_time = exposure_time if exposure_time is not None else CONFIG_INI.getfloat(self.config_id,
                                                                                                 'exposure_time')

        # Store the camera's detector shape.
        detector_max_x = CONFIG_INI.getint(self.config_id, 'detector_width')
        detector_max_y = CONFIG_INI.getint(self.config_id, 'detector_length')

        if self.full_image:
            self.log.info("Taking full", detector_max_x, "x", detector_max_y, "image, ignoring region of interest params.")
            fi_params = {'StartX': '0', 'StartY': '0',
                         'NumX': str(detector_max_x), 'NumY': str(detector_max_y),
                         'CoolerState': str(self.cooler_state)}
            r = requests.get(self.base_url + "ImagerSetSettings.cgi", params=fi_params, timeout=self.timeout)
            r.raise_for_status()
            return

        # Check for errors, log before exiting.
        error_flag = False

        # Unlike ZWO, width and height are in camera pixels, unaffected by bins
        if self.bins != 1:
            # set the parameters for binning
            bin_params = {'BinX': str(self.bins), 'BinY': str(self.bins)}
            r = requests.get(self.base_url + "ImagerSetSettings.cgi", params=bin_params, timeout=self.timeout)
            r.raise_for_status()

        # Derive the start x/y position of the region of interest, and check that it falls on the detector.
        derived_start_x = self.subarray_x - (self.width // 2)
        derived_start_y = self.subarray_y - (self.height // 2)
        derived_end_x = self.subarray_x + (self.width // 2)
        derived_end_y = self.subarray_y + (self.height // 2)

        if derived_start_x > detector_max_x or derived_start_x < 0:
            self.log.error("Derived start x coordinate is off the detector ( max", detector_max_x - 1, "):", derived_start_x)
            error_flag = True

        if derived_start_y > detector_max_y or derived_start_y < 0:
            self.log.error("Derived start y coordinate is off the detector ( max", detector_max_y - 1, "):", derived_start_y)
            error_flag = True

        if derived_end_x > detector_max_x or derived_end_x < 0:
            self.log.error("Derived end x coordinate is off the detector ( max", detector_max_x - 1, "):", derived_end_x)
            error_flag = True

        if derived_end_y > detector_max_y or derived_end_y < 0:
            self.log.error("Derived end y coordinate is off the detector ( max", detector_max_y - 1, "):", derived_end_y)
            error_flag = True

        if self.full_image:
            self.log.info("Taking full", detector_max_x, "x", detector_max_y, "image, ignoring region of interest params.")
            fi_params = {'StartX': '0', 'StartY': '0',
                         'NumX': str(detector_max_x), 'NumY': str(detector_max_y),
                         'CoolerState': '0'}
            r = requests.get(self.base_url + "ImagerSetSettings.cgi", params=fi_params, timeout=self.timeout)
            r.raise_for_status()
        else:
            if error_flag:
                sys.exit("Exiting. Correct errors in the config.ini file or input parameters.")

        # Set Region of Interest.
        if not full_image:
            roi_params = {'StartX': str(derived_start_x), 'StartY': str(derived_start_y),
                          'NumX': str(self.width), 'NumY': str(self.height),
                          'CoolerState': str(self.cooler_state)}
            r = requests.get(self.base_url + "ImagerSetSettings.cgi", params=roi_params, timeout=self.timeout)
            r.raise_for_status()

    def __check_imager_state(self):
        """Utility function to get the current state of the camera.
           Make an HTTP request and check for good response, then return the value of the response.
           Will raise an exception on an HTTP failure."""
        r = requests.get(self.base_url + "ImagerState.cgi", timeout=self.timeout)
        r.raise_for_status()
        return int(r.text)

    def __check_image_status(self):
        """Utility function to check that the camera is ready to expose.
           Make an HTTP request and check for good response, then return the value of hte response.
           Will raise an exception on an HTTP failure."""
        r = requests.get(self.base_url + "ImagerImageReady.cgi", timeout=self.timeout)
        r.raise_for_status()
        return int(r.text)

    def __capture(self, exposure_time):
        """Utility function to start and exposure and wait until the camera has completed the
           exposure.  Then wait for the image to be ready for download, and download it.
           Assumes the parameters for the exposure are already set."""

        # start an exposure.
        params = {'Duration': exposure_time.to(units.second).magnitude,
                  'FrameType': self.FRAME_TYPE_LIGHT}
        r = requests.get(self.base_url + "ImagerStartExposure.cgi",
                         params=params,
                         timeout=self.timeout)
        r.raise_for_status()
        imager_state = self.IMAGER_STATE_EXPOSING

        # wait until imager has taken an image
        while imager_state > self.IMAGER_STATE_IDLE:
            catkit.util.sleep(self.min_delay)  # limit the rate at which requests go to the camera
            imager_state = self.__check_imager_state()
            if imager_state == self.IMAGER_STATE_ERROR:
                # an error has occurred
                self.log.error('Imager error during exposure')
                raise Exception("Camera reported error during exposure.")

        # at loop exit, the image should be available
        image_status = self.__check_image_status()
        if image_status != self.IMAGE_AVAILABLE:
            self.log.error('No image after exposure')
            raise Exception("Camera reported no image available after exposure.")

        # get the image
        r = requests.get(self.base_url + "ImagerData.bin", timeout=self.timeout)
        r.raise_for_status()
        image = np.reshape(np.frombuffer(r.content, np.uint16), (self.width // self.bins, self.height // self.bins))

        # Apply rotation and flip to the image based on config.ini file.
        theta = CONFIG_INI.getint(self.config_id, 'image_rotation')
        fliplr = CONFIG_INI.getboolean(self.config_id, 'image_fliplr')
        image = catkit.util.rotate_and_flip_image(image, theta, fliplr)

        return image
