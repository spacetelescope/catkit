from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

from builtins import *

from hicat.interfaces.Camera import Camera
from hicat.config import CONFIG_INI
from hicat import units, quantity
from hicat.hardware import testbed_state
from astropy.io import fits
import numpy as np
import os
import zwoasi
import sys


"""Implementation of Hicat.Camera ABC that provides interface and context manager for using ZWO cameras."""


class ZwoCamera(Camera):
    def initialize(self, *args, **kwargs):
        """Opens connection with camera and returns the camera manufacturer specific object.
           Uses the config_id to look up parameters in the config.ini."""
        env_filename = os.getenv('ZWO_ASI_LIB')
        try:
            zwoasi.init(env_filename)
        except Exception:
            # Library already initialized, continuing...
            pass

        # Attempt to find USB camera.
        num_cameras = zwoasi.get_num_cameras()
        if num_cameras == 0:
            print('No cameras found')
            sys.exit(0)

        cameras_found = zwoasi.list_cameras()  # Model names of the connected cameras.
        # Get camera id and name.
        camera_name = CONFIG_INI.get(self.config_id, 'camera_name')

        camera_index = None
        camera_index = cameras_found.index(camera_name)
        if camera_index is None:
            raise Exception("Camera " + camera_name + " not found.")

        # Create a camera object using the zwoasi library.
        camera = zwoasi.Camera(camera_index)

        # Get all of the camera controls.
        controls = camera.get_controls()

        # Restore all controls to default values, in case any other application modified them.
        for c in controls:
            camera.set_control_value(controls[c]['ControlType'], controls[c]['DefaultValue'])

        # Set bandwidth overload control to minvalue.
        camera.set_control_value(zwoasi.ASI_BANDWIDTHOVERLOAD, camera.get_controls()['BandWidth']['MinValue'])

        try:
            # Force any single exposure to be halted
            camera.stop_video_capture()
            camera.stop_exposure()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            pass

        # Set image format to be RAW16, although camera is only 12-bit.
        camera.set_image_type(zwoasi.ASI_IMG_RAW16)
        return camera

    def close(self):
        """Close camera connection"""
        self.camera.close()

    def take_exposures(self, exposure_time, num_exposures, path="", filename="",
                            fits_header_dict=None, center_x=None, center_y=None, width=None, height=None,
                            gain=None, full_image=None, bins=None, resume=False, write_out_data=True):#*args, **kwargs):
        if write_out_data:
            self.take_exposures_fits(exposure_time, num_exposures, path, filename,
                            fits_header_dict, center_x, center_y, width, height,
                            gain, full_image, bins, resume)#*args, **kwargs)
            return

        else:
            img_list = self.take_exposures_data(exposure_time, num_exposures,
                            center_x, center_y, width, height,
                            gain, full_image, bins)#*args, **kwargs)
            return img_list



    def take_exposures_fits(self, exposure_time, num_exposures, path, filename,
                            fits_header_dict=None, center_x=None, center_y=None, width=None, height=None,
                            gain=None, full_image=None, bins=None, resume=False):
        """
        Takes exposures, saves as FITS files and returns list of file paths. The keyword arguments
        are used as overrides to the default values stored in config.ini.
        :param exposure_time: Pint quantity for exposure time, otherwise in microseconds.
        :param num_exposures: Number of exposures.
        :param path: Path of the directory to save fits file to.
        :param filename: Name for file.
        :param fits_header_dict: Dictionary of extra attributes to stuff into fits header.
        :param center_x: X coordinate of center pixel.
        :param center_y: Y coordinate of center pixel.
        :param width: Desired width of image.
        :param height: Desired height of image.
        :param gain: Gain of ZWO camera (volts).
        :param full_image: Boolean for whether to take a full image.
        :param bins: Integer value for number of bins.
        :param resume: If True, will skip exposure if image exists on disk already.
        :return: List of file paths to the fits files created.
        """

        # Convert exposure time to contain units if not already a Pint quantity.
        if type(exposure_time) is not quantity:
            exposure_time = quantity(exposure_time, units.microsecond)

        self.__setup_control_values(exposure_time, center_x=center_x, center_y=center_y, width=width,
                                    height=height, gain=gain, full_image=full_image, bins=bins)

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

        filepath_list = []

        # Take exposure. Use Astropy to handle fits format.
        for i in range(num_exposures):

            # For multiple exposures append frame number to end of base file name.
            if num_exposures > 1:
                filename = file_root + "_frame" + str(i + 1) + file_ext
            full_path = os.path.join(path, filename)

            # If Resume is enabled, continue if the file already exists on disk.
            if resume and os.path.isfile(full_path):
                print("File already exists: " + full_path)
                continue

            # Take exposure.
            img = self.__capture(exposure_time)

            # Create a PrimaryHDU object to encapsulate the data.
            hdu = fits.PrimaryHDU(img)

            # Add headers.
            hdu.header["EXP_TIME"] = (exposure_time.to(units.microseconds).magnitude, "microseconds")
            hdu.header["CAMERA"] = (self.config_id, "Model of camera, correlates to entry in ini")
            hdu.header["GAIN"] = self.gain
            hdu.header["BINS"] = self.bins
            hdu.header["FRAME"] = i + 1
            hdu.header["FILENAME"] = filename

            # Add testbed state metadata.
            for entry in testbed_state.create_metadata():
                if len(entry.name_8chars) > 8:
                    print("Fits Header Keyword: " + entry.name_8chars +
                          " is greater than 8 characters and will be truncated.")
                if len(entry.comment) > 47:
                    print("Fits Header comment for " + entry.name_8chars +
                          " is greater than 47 characters and will be truncated.")
                hdu.header[entry.name_8chars[:8]] = (entry.value, entry.comment)

            # Add extra header keywords passed in.
            if fits_header_dict:
                for k, v in fits_header_dict.items():
                    if len(k) > 8:
                        print("Fits Header Keyword: " + k + " is greater than 8 characters and will be truncated.")
                    hdu.header[k[:8]] = v

            # Create a HDUList to contain the newly created primary HDU, and write to a new file.
            fits.HDUList([hdu])
            hdu.writeto(full_path, overwrite=True)
            print("wrote " + full_path)
            filepath_list.append(full_path)

        return filepath_list

    def take_exposures_data(self, exposure_time, num_exposures,
                            center_x=None, center_y=None, width=None, height=None,
                            gain=None, full_image=None, bins=None):
        """Takes exposures and returns list of numpy arrays."""

        # Convert exposure time to contain units if not already a Pint quantity.
        if type(exposure_time) is not quantity:
            exposure_time = quantity(exposure_time, units.microsecond)

        self.__setup_control_values(exposure_time, center_x=center_x, center_y=center_y, width=width,
                                    height=height, gain=gain, full_image=full_image, bins=bins)
        img_list = []

        # Take exposures and add to list.
        for i in range(num_exposures):
            img = self.__capture(exposure_time)
            img_list.append(img)

        return img_list

    def __setup_control_values(self, exposure_time, center_x=None, center_y=None, width=None, height=None,
                               gain=None, full_image=None, bins=None):
        """Applies control values found in the config.ini unless overrides are passed in, and does error checking."""

        # Load values from config.ini into variables, and override with keyword args when applicable.
        center_x = center_x if center_x is not None else CONFIG_INI.getint(self.config_id, 'center_x')
        center_y = center_y if center_y is not None else CONFIG_INI.getint(self.config_id, 'center_y')
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
            print("Taking full", detector_max_x, "x", detector_max_y, "image, ignoring region of interest params.")
            return

        # Check for errors, print them all out before exiting.
        error_flag = False

        # Check that width and height are multiples of 8
        if width % 8 != 0:
            print("Width is not a multiple of 8:", width)
            error_flag = True
        if height % 8 != 0:
            print("Height is not a multiple of 8:", height)
            error_flag = True

        # Convert to binned units
        if bins != 1:
            # For debugging
            # print("Converting to binned units: bins =", bins)

            center_x //= bins
            center_y //= bins
            width //= bins
            height //= bins

        # Derive the start x/y position of the region of interest, and check that it falls on the detector.
        derived_start_x = center_x - (width // 2)
        derived_start_y = center_y - (height // 2)
        derived_end_x = center_x + (width // 2)
        derived_end_y = center_y + (height // 2)

        if derived_start_x > detector_max_x or derived_start_x < 0:
            print("Derived start x coordinate is off the detector ( max", detector_max_x - 1, "):", derived_start_x)
            error_flag = True

        if derived_start_y > detector_max_y or derived_start_y < 0:
            print("Derived start y coordinate is off the detector ( max", detector_max_y - 1, "):", derived_start_y)
            error_flag = True

        if derived_end_x > detector_max_x or derived_end_x < 0:
            print("Derived end x coordinate is off the detector ( max", detector_max_x - 1, "):", derived_end_x)
            error_flag = True

        if derived_end_y > detector_max_y or derived_end_y < 0:
            print("Derived end y coordinate is off the detector ( max", detector_max_y - 1, "):", derived_end_y)
            error_flag = True

        if full_image:
            print("Taking full", detector_max_x, "x", detector_max_y, "image, ignoring region of interest params.")
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

        # Apply flips to the image based on config.ini file
        flip_x = CONFIG_INI.getboolean(self.config_id, 'flip_x')
        flip_y = CONFIG_INI.getboolean(self.config_id, 'flip_y')

        if flip_x:
            image = np.flipud(image)
        if flip_y:
            image = np.fliplr(image)

        return image.astype(np.dtype(np.int))
