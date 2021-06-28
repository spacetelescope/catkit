import importlib
import logging

import numpy as np

from catkit.interfaces.Camera import Camera
from catkit.catkit_types import MetaDataEntry, units, quantity
import catkit.util
from catkit.config import CONFIG_INI


class LazyLoadLibraryMeta(type):
    # Forward any call to a function to the library. Autoload the library upon first call.
    def __getattr__(cls, name):
        lib = cls.load_library()

        return getattr(lib, name)


class FlirLibrary(metaclass=LazyLoadLibraryMeta):
    _library = None

    # The class is not an abstract method.
    __isabstractmethod__ = False

    @classmethod
    def load_library(cls):
        if cls._library is not None:
            return cls._library

        cls._library = importlib.import_module('PySpin', 'PySpin')

        return cls._library


def _create_property(flir_property_name, read_only=False):
    def getter(self):
        return getattr(self.cam, flir_property_name).GetValue()

    if read_only:
        setter = None
    else:
        def setter(self, value):
            getattr(self.cam, flir_property_name).SetValue(value)

    return property(getter, setter)


def _create_enum_property(flir_property_name, enum_name):
    def getter(self):
        value = getattr(self.cam, flir_property_name).GetValue()

        # Reverse search in enum dictionary.
        for key, val in getattr(self, enum_name).items():
            if value == val:
                return key

        raise KeyError('Value not recognized.')

    def setter(self, value):
        value = getattr(self, enum_name)[value]
        getattr(self.cam, flir_property_name).SetValue(value)

    return property(getter, setter)


class FlirCamera(Camera):
    instrument_lib = FlirLibrary

    _system = None
    _system_ref_count = 0

    @classmethod
    def _create_system(cls):
        if cls._system is None:
            cls._system = cls.instrument_lib.System.GetInstance()

        cls._system_ref_count += 1

    @classmethod
    def _destroy_system(cls):
        cls._system_ref_count -= 1

        if cls._system_ref_count == 0:
            cls._system.ReleaseInstance()
            cls._system = None

    def initialize(self):
        self.log = logging.getLogger(__name__)

        # Set up enum dictionaries
        self.pixel_format_enum = {'mono8': self.instrument_lib.PixelFormat_Mono8,
                                  'mono12p': self.instrument_lib.PixelFormat_Mono12p,
                                  'mono16': self.instrument_lib.PixelFormat_Mono16}

        self.adc_bit_depth_enum = {'8bit': self.instrument_lib.AdcBitDepth_Bit8,
                                   '10bit': self.instrument_lib.AdcBitDepth_Bit10,
                                   '12bit': self.instrument_lib.AdcBitDepth_Bit12,
                                   '14bit': self.instrument_lib.AdcBitDepth_Bit14}

    def _open(self):
        serial_number = CONFIG_INI.get(self.config_id, 'serial_number')

        # Obtain singleton Flir system object
        self._create_system()

        self.cam_list = self._system.GetCameras()
        self.cam = self.cam_list.GetBySerial(serial_number)

        try:
            self.cam.Init()
        except:
            raise RuntimeError(f'Error during intialization of {self.config_id}. Is the camera connected?')

        # Make sure that the camera is stopped.
        self.cam.BeginAcquisition()
        self.cam.EndAcquisition()

        # Turn off indicator led
        self.cam.DeviceIndicatorMode.SetValue(self.instrument_lib.DeviceIndicatorMode_ErrorStatus)

        # Set standard exposure settings
        self.cam.ExposureAuto.SetValue(self.instrument_lib.ExposureAuto_Off)
        self.cam.ExposureMode.SetValue(self.instrument_lib.ExposureMode_Timed)
        self.cam.GainAuto.SetValue(self.instrument_lib.GainAuto_Off)
        self.cam.GammaEnable.SetValue(False)
        self.cam.BlackLevelClampingEnable.SetValue(True)
        self.cam.BlackLevel.SetValue(5)
        self.cam.AcquisitionMode.SetValue(self.instrument_lib.AcquisitionMode_Continuous)
        self.cam.TLStream.StreamBufferHandlingMode.SetValue(self.instrument_lib.StreamBufferHandlingMode_NewestOnly)
        #self.cam.StreamBufferHandlingMode.SetValue(self.instrument_lib.StreamBufferHandlingMode_NewestOnly)

        #nodemap = self.cam.GetTLStreamNodeMap()
        #node = self.instrument_lib.CEnumerationPtr(nodemap.GetNode('StreamBufferHandlingMode'))
        #newest_only = node.GetEntryByName('NewestOnly')
        #node.SetIntValue(newest_only.GetValue())

        # Turn off triggering
        self.cam.TriggerMode.SetValue(self.instrument_lib.TriggerMode_Off)

        self.width = int(CONFIG_INI.get(self.config_id, 'width'))
        self.height = int(CONFIG_INI.get(self.config_id, 'height'))
        self.offset_x = int(CONFIG_INI.get(self.config_id, 'offset_x'))
        self.offset_y = int(CONFIG_INI.get(self.config_id, 'offset_y'))

        self.pixel_format = CONFIG_INI.get(self.config_id, 'pixel_format')
        self.adc_bit_depth = CONFIG_INI.get(self.config_id, 'adc_bit_depth')

        self.exposure_time = float(CONFIG_INI.get(self.config_id, 'exposure_time'))
        self.gain = float(CONFIG_INI.get(self.config_id, 'gain'))

        # Do not return self.cam, due to reference counting by PySpin.
        return True

    def _close(self):
        try:
            self.cam.EndAcquisition()
        except self.instrument_lib.SpinnakerException as e:
            if e.errorcode == -1002:
                # Camera was not running. We can safely ignore.
                pass
            else:
                self.log.error(f'PySpin error: {e.errorcode}')

        self.cam.DeInit()
        self.cam = None
        self.cam_list.Clear()

        self._destroy_system()

    exposure_time = _create_property('ExposureTime')
    gain = _create_property('Gain')

    width = _create_property('Width')
    height = _create_property('Height')
    offset_x = _create_property('OffsetX')
    offset_y = _create_property('OffsetY')

    temperature = _create_property('DeviceTemperature', read_only=True)

    pixel_format = _create_enum_property('PixelFormat', 'pixel_format_enum')
    adc_bit_depth = _create_enum_property('AdcBitDepth', 'adc_bit_depth_enum')

    @property
    def device_name(self):
        return self.cam.TLDevice.DeviceModelName.GetValue()

    def stream_exposures(self, exposure_time, num_exposures, extra_metadata=None):
        if not type(exposure_time) in [int, float]:
            exposure_time_us = exposure_time.to(units.microsecond).m
        else:
            exposure_time_us = exposure_time

        self.exposure_time = exposure_time_us

        meta_data = [MetaDataEntry("Exposure Time", "EXP_TIME", exposure_time_us, "microseconds")]
        meta_data.append(MetaDataEntry("Camera", "CAMERA", self.device_name, "Camera model, correlates to entry in ini"))
        meta_data.append(MetaDataEntry("Gain", "GAIN", self.gain, "Gain for camera"))

        if extra_metadata is not None:
            if isinstance(extra_metadata, list):
                meta_data.extend(extra_metadata)
            else:
                meta_data.append(extra_metadata)

        try:
            self.cam.BeginAcquisition()
            frame_count = 0

            if self.pixel_format == 'mono8':
                pixel_format = self.instrument_lib.PixelFormat_Mono8
            else:
                pixel_format = self.instrument_lib.PixelFormat_Mono16

            while frame_count < num_exposures:
                try:
                    image_result = self.cam.GetNextImage(100)
                except self.instrument_lib.SpinnakerException as e:
                    if e.errorcode == -1011:
                        # The timeout was triggered. Nothing to worry about.
                        continue
                    elif e.errorcode == -1010:
                        # The camera is not streaming anymore.
                        break
                    raise

                if image_result.IsIncomplete():
                    continue

                img = image_result.Convert(pixel_format).GetData().astype(np.float32)
                img = img.reshape((image_result.GetHeight(), image_result.GetWidth()))

                try:
                    yield img, meta_data
                    frame_count += 1
                finally:
                    image_result.Release()
        finally:
            self.cam.EndAcquisition()

    def take_exposures(self, exposure_time, num_exposures, path=None, filename=None, return_metadata=False, raw_skip=0, extra_metadata=None):
        images = []

        for img, meta in self.stream_exposures(exposure_time, num_exposures, extra_metadata):
            images.append(img)

        if path is not None:
            catkit.util.save_images(images, meta, path=path, base_filename=filename, raw_skip=raw_skip)

        # TODO: Nuke this and always return both, eventually returning a HDUList (HICAT-794).
        if return_metadata:
            return images, meta
        else:
            return images
