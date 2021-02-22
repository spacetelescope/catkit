import os
import sys

import numpy as np
import zwoasi

from catkit.config import CONFIG_INI

from catkit.catkit_types import MetaDataEntry, units, quantity
from catkit.interfaces.Camera import Camera
import catkit.util


"""Implementation of Hicat.Camera ABC that provides interface and context manager for using ZWO cameras."""


class ZwoCamera(Camera):

    instrument_lib = zwoasi
    __ZWO_ASI_LIB = 'ZWO_ASI_LIB'

    @classmethod
    def load_asi_lib(cls):
        # Importing zwoasi doesn't hook it up to the backend driver, we have to unfortunately do this.
        # This is achieved by zwoasi.init(<file to ASI SDK lib>)

        # NOTE: The ZWO ASI SDK can be downloaded from https://astronomy-imaging-camera.com/software-drivers
        # Windows requires additional drivers also from https://astronomy-imaging-camera.com/software-drivers

        try:
            __env_filename = os.getenv(cls.__ZWO_ASI_LIB)

            if not __env_filename:
                raise OSError("Environment variable '{}' doesn't exist. Create and point to ASICamera2 lib".format(cls.__ZWO_ASI_LIB))
            if not os.path.exists(__env_filename):
                raise OSError("File not found: '{}' -> '{}'".format(cls.__ZWO_ASI_LIB, __env_filename))

            try:
                cls.instrument_lib.init(__env_filename)
            except cls.instrument_lib.ZWO_Error as error:
                if str(error) == 'Library already initialized':  # weak but better than nothing...
                    # Library already initialized, continuing...
                    pass
                else:
                    raise
        except Exception as error:
            raise ImportError(f"Failed to load {cls.__ZWO_ASI_LIB} library backend to {cls.instrument_lib.__qualname__}") from error

    def initialize(self):
        """Uses the config_id to look up parameters in the config.ini."""

        # Importing zwoasi doesn't hook it up to the backend driver, we have to unfortunately do this.
        self.load_asi_lib()

        # Pull flip parameters
        self.theta = CONFIG_INI.getint(self.config_id, 'image_rotation')
        self.fliplr = CONFIG_INI.getboolean(self.config_id, 'image_fliplr')

    def _open(self):

        # Attempt to find USB camera.
        num_cameras = self.instrument_lib.get_num_cameras()
        if num_cameras == 0:
            self.log.error('No cameras found')
            sys.exit(0)

        # Get camera id and name.
        camera_name = CONFIG_INI.get(self.config_id, 'camera_name')
        cameras_found = self.instrument_lib.list_cameras()  # Model names of the connected cameras.
        camera_index = cameras_found.index(camera_name)

        # Create a camera object using the zwoasi library.
        camera = self.instrument_lib.Camera(camera_index)
        self.log.info("Opened connection to camera: " + self.config_id)

        # Assign this here and now since we touch within this func and may trigger an exception.
        # Assigning this here will facilitate in correct closure.
        self.instrument = camera
        # Alias for backward compatibility.
        self.camera = self.instrument

        # Get all of the camera controls.
        controls = self.instrument.get_controls()

        # Restore all controls to default values, in case any other application modified them.
        for c in controls:
            self.instrument.set_control_value(controls[c]['ControlType'], controls[c]['DefaultValue'])

        # Set bandwidth overload control to minvalue.
        self.instrument.set_control_value(self.instrument_lib.ASI_BANDWIDTHOVERLOAD, camera.get_controls()['BandWidth']['MinValue'])

        # noinspection PyBroadException
        try:
            # Force any single exposure to be halted
            self.instrument.stop_video_capture()
            self.instrument.stop_exposure()
        except Exception:
            # Catch and hide exceptions that get thrown if the camera rejects the stop commands.
            pass

        # Set image format to be RAW16, although camera is only 12-bit.
        self.instrument.set_image_type(self.instrument_lib.ASI_IMG_RAW16)

        return self.instrument

    def __capture(self, initial_sleep):
        """ Takes an image.

        WARNING: This func does NOT set the exposure time!

        Parameters
        ----------
        initial_sleep : Pint quantity
            How long to sleep until exposure is complete. I.e., initial_sleep >= exposure_time.

        Returns
        -------
        image : np.array of floats
            Array of floats making up the image.
        """

        # Passing the initial_sleep and poll values prevent crashes. DO NOT REMOVE!!!
        poll = quantity(0.1, units.second)
        try:
            image = self.instrument.capture(initial_sleep=initial_sleep.to(units.second).magnitude, poll=poll.magnitude)
        except self.instrument_lib.ZWO_CaptureError as error:
            # Maps to:
            # https://github.com/stevemarple/python-zwoasi/blob/1aadf7924dd1cb3b8587d97689d82cd5f1a0b5f6/zwoasi/__init__.py#L889-L893
            if error.exposure_status == 3:
                raise RuntimeError("Exposure error: camera already in use, please close all other uses, e.g., SharpCap.") from error
            raise RuntimeError(f"Exposure status: {error.exposure_status}") from error
        return image.astype(np.dtype(np.float32))

    def __capture_and_orient(self, initial_sleep, theta, fliplr):
        """ Takes an image and flips according to theta and l/r input.

        WARNING: This func does NOT set the exposure time!

        Parameters
        ----------
        initial_sleep : int, float, Pint quantity
            How long to sleep until exposure is complete. I.e., initial_sleep >= exposure_time.
        theta : float
            How many degrees to rotate the image.
        fliplr : bool
            Whether to flip left/right.

        Returns
        -------
        image : np.array of floats
            Array of floats making up the image.
        """

        unflipped_image = self.__capture(initial_sleep=initial_sleep)
        image = catkit.util.rotate_and_flip_image(unflipped_image, theta, fliplr)
        return image

    def __capture_video(self, num_exposures, timeout):
        """ Take a number of images.

        WARNING: This func does NOT set the exposure time!

        Parameters
        ----------
        num_exposures : int
            The number of exposures to take.
        timeout : Pint quantity
            How long to wait for an image. Afterwards a timeout exception is raised.

        Returns
        -------
        images : list of (np.array of floats)
            All captured images in a list.
        """
        timeout_in_ms = timeout.to(units.millisecond).magnitude
        images = []

        self.instrument.start_video_capture()

        try:
            for i in range(num_exposures):
                img = self.instrument.capture_video_frame(timeout=timeout_in_ms)

                images.append(img.astype(np.dtype(np.float32)))
        finally:
            # Stop exposures. The stop_exposure() might not be necessary, but there's no
            # harm in calling it anyway.
            self.instrument.stop_video_capture()
            self.instrument.stop_exposure()

        return images

    def __capture_video_and_orient(self, num_exposures, timeout, theta, fliplr):
        """ Takes a number of images and flips each according to theta and l/r input.

        WARNING: This func does NOT set the exposure time!

        Parameters
        ----------
        num_exposures : int
            The number of exposures to take.
        timeout : Pint quantity
            How long to wait for an image. Afterwards a timeout exception is raised.
        theta : float
            How many degrees to rotate the image.
        fliplr : bool
            Whether to flip left/right.

        Returns
        -------
        images : list of (np.array of floats)
            All captured images in a list.
        """
        images = self.__capture_video(num_exposures, timeout)

        oriented_images = [catkit.util.rotate_and_flip_image(unflipped_image, theta, fliplr) for unflipped_image in images]

        return oriented_images

    def _close(self):
        """Close camera connection"""
        self.log.info("Closing camera connection.")
        self.instrument.close()

    def take_exposures(self, exposure_time, num_exposures,
                       file_mode=False, raw_skip=0, path=None, filename=None,
                       extra_metadata=None,
                       return_metadata=False,
                       subarray_x=None, subarray_y=None, width=None, height=None, gain=None, full_image=None,
                       bins=None):
        """ Wrapper to take exposures and also save them if `file_mode` is used. """

        images, meta = self.just_take_exposures(exposure_time=exposure_time,
                                                num_exposures=num_exposures,
                                                extra_metadata=extra_metadata,
                                                full_image=full_image, subarray_x=subarray_x, subarray_y=subarray_y,
                                                width=width, height=height,
                                                gain=gain,
                                                bins=bins)

        if file_mode:
            catkit.util.save_images(images, meta, path=path, base_filename=filename, raw_skip=raw_skip)

        # TODO: Nuke this and always return both, eventually returning a HDUList (HICAT-794).
        if return_metadata:
            return images, meta
        else:
            return images

    def just_take_exposures(self, exposure_time, num_exposures,
                            extra_metadata=None,
                            subarray_x=None, subarray_y=None, width=None, height=None, gain=None, full_image=None,
                            bins=None, use_video_capture_mode=None):
        """
        Low level method to take exposures using a Zwo camera. By default keeps image data in.

        :param exposure_time: Pint quantity for exposure time, otherwise in microseconds.
        :param num_exposures: Number of exposures.
        :param extra_metadata: Will be appended to metadata created and written to fits header.
        :param subarray_x: X coordinate of center pixel of the subarray.
        :param subarray_y: Y coordinate of center pixel of the subarray.
        :param width: Desired width of image.
        :param height: Desired height of image.
        :param gain: Gain of ZWO camera (volts).
        :param full_image: Boolean for whether to take a full image.
        :param bins: Integer value for number of bins.
        :param use_video_capture_mode: Boolean for whether to use video capture or snapshot mode. Default is False.
        :return: Two parameters: Image list (numpy data or paths), Metadata list of MetaDataEntry objects.
        """

        # Set default for using video capture mode.
        if use_video_capture_mode is None:
            use_video_capture_mode = False

        # Convert exposure time to contain units if not already a Pint quantity.
        # if not isintance(quantity):
        if type(exposure_time) is int or type(exposure_time) is float:
            exposure_time = quantity(exposure_time, units.microsecond)

        # Set control values on the ZWO camera.
        # WARNING! This is the only place that the exposure time is set.
        self.__setup_control_values(exposure_time, subarray_x=subarray_x, subarray_y=subarray_y, width=width,
                                    height=height, gain=gain, full_image=full_image, bins=bins)

        # Create metadata from extra_metadata input.
        meta_data = [MetaDataEntry("Exposure Time", "EXP_TIME", exposure_time.to(units.microsecond).m, "microseconds")]
        meta_data.append(MetaDataEntry("Camera", "CAMERA", self.config_id, "Camera model, correlates to entry in ini"))
        meta_data.append(MetaDataEntry("Gain", "GAIN", self.gain, "Gain for camera"))
        meta_data.append(MetaDataEntry("Bins", "BINS", self.bins, "Binning for camera"))
        if extra_metadata is not None:
            if isinstance(extra_metadata, list):
                meta_data.extend(extra_metadata)
            else:
                meta_data.append(extra_metadata)

        # DATA MODE: Takes images and returns data and metadata (does not write anything to disk).
        if use_video_capture_mode:
            # Set timeout in ms to:
            # 2 x exposure time + 0.5sec
            # as per SDK recommendation
            timeout = 2 * exposure_time + quantity(0.5, units.second) # ms

            img_list = self.__capture_video_and_orient(num_exposures, timeout, theta=self.theta, fliplr=self.fliplr)
        else:
            img_list = []
            # Take exposures and add to list.
            for i in range(num_exposures):
                img = self.__capture_and_orient(initial_sleep=exposure_time, theta=self.theta, fliplr=self.fliplr)
                img_list.append(img)

        return img_list, meta_data

    def flash_id(self, new_id):
        """
        Flashes the camera memory to append a string at the end of the camera name.
        :param new_id:
        Ascii value of the string you want to append.
        Passing the value 49 will append (1) to the name.
        Passing the value 50 will append (2) to the name.
        """

        camera_info_before = self.instrument.get_camera_property()
        self.log.info("Before Flash:")
        self.log.info(camera_info_before["Name"])
        self.instrument.set_id(0, new_id)
        self.log.info("After Flash:")
        camera_info_after = self.instrument.get_camera_property()
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
        self.instrument.set_control_value(self.instrument_lib.ASI_GAIN, gain)
        self.instrument.set_control_value(self.instrument_lib.ASI_EXPOSURE, int(exposure_time.to(units.microsecond).magnitude))

        # Store the camera's detector shape.
        cam_info = self.instrument.get_camera_property()
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
            self.instrument.set_roi(start_x=derived_start_x,
                                start_y=derived_start_y,
                                width=width,
                                height=height,
                                image_type=self.instrument_lib.ASI_IMG_RAW16,
                                bins=bins)
