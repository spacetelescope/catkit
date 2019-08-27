from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from astropy.io import fits
import numpy as np
import logging
import os
import zwoasi
import sys

from ...hicat_types import MetaDataEntry, units, quantity
from ...interfaces.Camera import Camera
from ...config import CONFIG_INI
from ... import util
from ...hardware import testbed_state


"""Implementation of Hicat.Camera ABC that provides interface and context manager for using ZWO cameras."""


class ZwoCamera(Camera):

    log = logging.getLogger(__name__)

    def initialize(self, *args, **kwargs):
        """Opens connection with camera and returns the camera manufacturer specific object.
           Uses the config_id to look up parameters in the config.ini."""
        # noinspection PyBroadException

        # Attempt to find USB camera.
        num_cameras = zwoasi.get_num_cameras()
        if num_cameras == 0:
            self.log.error('No cameras found')
            sys.exit(0)

        cameras_found = zwoasi.list_cameras()  # Model names of the connected cameras.

        # Get camera id and name.
        camera_name = CONFIG_INI.get(self.config_id, 'camera_name')
        camera_index = cameras_found.index(camera_name)

        # Create a camera object using the zwoasi library.
        camera = zwoasi.Camera(camera_index)

        # Get all of the camera controls.
        controls = camera.get_controls()

        # Restore all controls to default values, in case any other application modified them.
        for c in controls:
            camera.set_control_value(controls[c]['ControlType'], controls[c]['DefaultValue'])

        # Set bandwidth overload control to minvalue.
        camera.set_control_value(zwoasi.ASI_BANDWIDTHOVERLOAD, camera.get_controls()['BandWidth']['MinValue'])

        # noinspection PyBroadException
        try:
            # Force any single exposure to be halted
            camera.stop_video_capture()
            camera.stop_exposure()
        except Exception:
            # Catch and hide exceptions that get thrown if the camera rejects the stop commands.
            pass

        # Set image format to be RAW16, although camera is only 12-bit.
        camera.set_image_type(zwoasi.ASI_IMG_RAW16)
        return camera

    def close(self):
        """Close camera connection"""
        self.camera.close()

    def take_exposures(self, exposure_time, num_exposures,
                       file_mode=False, raw_skip=0, path=None, filename=None,
                       extra_metadata=None,
                       resume=False,
                       return_metadata=False,
                       subarray_x=None, subarray_y=None, width=None, height=None, gain=None, full_image=None,
                       bins=None):
        """
        Low level method to take exposures using a Zwo camera. By default keeps image data in.

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
        :param gain: Gain of ZWO camera (volts).
        :param full_image: Boolean for whether to take a full image.
        :param bins: Integer value for number of bins.
        :return: Two parameters: Image list (numpy data or paths), Metadata list of MetaDataEntry objects.
        """

        # Convert exposure time to contain units if not already a Pint quantity.
        if type(exposure_time) is int or type(exposure_time) is float:
            exposure_time = quantity(exposure_time, units.microsecond)

        # Set control values on the ZWO camera.
        self.__setup_control_values(exposure_time, subarray_x=subarray_x, subarray_y=subarray_y, width=width,
                                    height=height, gain=gain, full_image=full_image, bins=bins)

        # Create metadata from testbed_state and add extra_metadata input.
        meta_data = [MetaDataEntry("Exposure Time", "EXP_TIME", exposure_time.to(units.microseconds).m, "microseconds")]
        meta_data.extend(testbed_state.create_metadata())
        meta_data.append(MetaDataEntry("Camera", "CAMERA", self.config_id, "Camera model, correlates to entry in ini"))
        meta_data.append(MetaDataEntry("Gain", "GAIN", self.gain, "Gain for camera"))
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

    def flash_id(self, new_id):
        """
        Flashes the camera memory to append a string at the end of the camera name.
        :param new_id:
        Ascii value of the string you want to append.
        Passing the value 49 will append (1) to the name.
        Passing the value 50 will append (2) to the name.
        """

        camera_info_before = self.camera.get_camera_property()
        self.log.info("Before Flash:")
        self.log.info(camera_info_before["Name"])
        self.camera.set_id(0, new_id)
        self.log.info("After Flash:")
        camera_info_after = self.camera.get_camera_property()
        self.log.info(camera_info_after["Name"])

    def __setup_control_values(self, exposure_time, subarray_x=None, subarray_y=None, width=None, height=None,
                               gain=None, full_image=None, bins=None):
        """Applies control values found in the config.ini unless overrides are passed in, and does error checking."""

        # Load values from config.ini into variables, and override with keyword args when applicable.
        subarray_x = subarray_x if subarray_x is not None else CONFIG_INI.getint(self.config_id, 'subarray_x')
        subarray_y = subarray_y if subarray_y is not None else CONFIG_INI.getint(self.config_id, 'subarray_y')
        width = width if width is not None else CONFIG_INI.getint(self.config_id, 'width')
        height = height if height is not None else CONFIG_INI.getint(self.config_id, 'height')
        gain = gain if gain is not None else CONFIG_INI.getint(self.config_id, 'gain')
        full_image = full_image if full_image is not None else CONFIG_INI.getboolean(self.config_id, 'full_image')
        bins = bins if bins is not None else CONFIG_INI.getint(self.config_id, 'bins')

        # Set some class attributes.
        self.gain = gain
        self.bins = bins

        # Set up our custom control values.
        self.camera.set_control_value(zwoasi.ASI_GAIN, gain)
        self.camera.set_control_value(zwoasi.ASI_EXPOSURE, int(exposure_time.to(units.microsecond).magnitude))

        # Store the camera's detector shape.
        cam_info = self.camera.get_camera_property()
        detector_max_x = cam_info['MaxWidth']
        detector_max_y = cam_info['MaxHeight']

        if full_image:
            #self.log.info("Taking full", detector_max_x, "x", detector_max_y, "image, ignoring region of interest params.")
            self.log.info("Taking full image, ignoring region of interest params.")
            return

        # Check for errors, log them all before exiting.
        error_flag = False

        # Check that width and height are multiples of 8
        if width % 8 != 0:
            self.log.error("Width is not a multiple of 8:", width)
            error_flag = True
        if height % 8 != 0:
            self.log.error("Height is not a multiple of 8:", height)
            error_flag = True

        # Convert to binned units
        if bins != 1:
            # For debugging
            # self.log.debug("Converting to binned units: bins =", bins)

            subarray_x //= bins
            subarray_y //= bins
            width //= bins
            height //= bins

        # Derive the start x/y position of the region of interest, and check that it falls on the detector.
        derived_start_x = subarray_x - (width // 2)
        derived_start_y = subarray_y - (height // 2)
        derived_end_x = subarray_x + (width // 2)
        derived_end_y = subarray_y + (height // 2)

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

        if full_image:
            self.log.error("Taking full", detector_max_x, "x", detector_max_y, "image, ignoring region of interest params.")
        else:
            if error_flag:
                sys.exit("Exiting. Correct errors in the config.ini file or input parameters.")

        # Set Region of Interest.
        if not full_image:
            self.camera.set_roi(start_x=derived_start_x,
                                start_y=derived_start_y,
                                width=width,
                                height=height,
                                image_type=zwoasi.ASI_IMG_RAW16,
                                bins=bins)

    def __capture(self, exposure_time):

        # Passing the initial_sleep and poll values prevent crashes. DO NOT REMOVE!!!
        poll = quantity(0.1, units.second)
        image = self.camera.capture(initial_sleep=exposure_time.to(units.second).magnitude, poll=poll.magnitude)

        # Apply rotation and flip to the image based on config.ini file.
        theta = CONFIG_INI.getint(self.config_id, 'image_rotation')
        fliplr = CONFIG_INI.getboolean(self.config_id, 'image_fliplr')
        image = util.rotate_and_flip_image(image, theta, fliplr)

        return image.astype(np.dtype(np.int))
