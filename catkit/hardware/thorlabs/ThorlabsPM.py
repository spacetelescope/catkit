import ctypes
import glob
import os
import sys

from catkit.config import CONFIG_INI
from catkit.interfaces.PowerMeter import PowerMeter
import catkit.util


class ThorlabsPMInstrumentMeta(type):
    # Forward any call to a function to the PM library. Autoload the library upon first call.
    def __getattr__(cls, name):
        lib = cls.load_library()

        return getattr(lib, name)


class ThorlabsPMInstrument(metaclass=ThorlabsPMInstrumentMeta):
    _library = None

    @classmethod
    def load_library(cls):
        if cls._library is not None:
            return cls._library

        # Find TLPM_64.dll - the path to which needs to be added to PYTHONPATH.
        # E.g. C:/Program Files/IVI Foundation/VISA/Win64/Bin/TLPM_64.dll.
        library_name = "TLPM_64.dll"  # Yep, this is Windows specific.
        library_path = None

        for path in sys.path:
            library_path = glob.glob(os.path.join(path, library_name))

            if library_path:
                break

        if not library_path:
            raise ImportError("TLPM: Failed to locate '{}' - add path to PYTHONPATH".format(library_name))

        # Now load the found library.
        try:
            cls._library = ctypes.cdll.LoadLibrary(library_path[0])
        except Exception as error:
            cls._library = None
            raise ImportError("TLPM: Failed to import '{}' library @ '{}'".format(library_name, library_path)) from error

        return cls._library


class ThorlabsPM(PowerMeter):
    instrument_lib = ThorlabsPMInstrument

    _BUFFER_SIZE = 1024

    def initialize(self, serial_number):
        self.serial_number = serial_number

    def _open(self):
        self.instrument = ctypes.c_void_p(None)

        # Find the desired device resource name. This is not just the SN#.
        available_devices = self.find_all()
        device_names = [device for device in available_devices if self.serial_number in device]

        if not device_names:
            raise OSError("TLPM: device not found - SN# '{}'".format(self.serial_number))

        if len(device_names) > 1:
            raise OSError("TLPM: found multiple devices with the same SN# '{}'".format(self.serial_number))

        self.device_name = device_names[0]

        # int TLPM_init(char *resourceName, bool IDQuery, bool resetDevice, void **vi)
        # use ctypes.pointer() to allow the emulator to modify this parameter
        status = self.instrument_lib.TLPM_init(self.device_name.encode(), True, True, ctypes.pointer(self.instrument))
        if status or self.instrument.value is None:
            raise OSError("TLPM: Failed to connect - '{}'".format(self.get_error_message(status)))

        return self.instrument

    def get_error_message(self, status_code):
        """Convert error status to error message."""
        error_message = ctypes.create_string_buffer(self._BUFFER_SIZE)

        # int TLPM_errorMessage(void *vi, int statusCode, char description[])
        status = self.instrument_lib.TLPM_errorMessage(None, status_code, error_message)
        if status:
            raise OSError("TLPM: Ironically failed to get error message - '{}'".format(self.get_error_message(status)))

        return error_message.value.decode()

    @classmethod
    def create(cls, config_id):
        return cls(config_id=config_id, serial_number=CONFIG_INI.get(config_id, "serial_number"))

    def find_all(self):
        """Find all connected PM devices."""
        # First find the total number of connected PM devices.
        device_count = ctypes.c_int(0)

        # int TLPM_findRsrc(void *vi, int *resourceCount)
        # use ctypes.pointer() to allow the emulator to modify this parameter
        status = self.instrument_lib.TLPM_findRsrc(None, ctypes.pointer(device_count))
        if status:
            raise ImportError("TLPM: Failed when trying to find connected devices - '{}'".format(self.get_error_message(status)))

        # Then get their resource names.
        available_devices = []

        for i in range(device_count.value):
            resource_name = ctypes.create_string_buffer(self._BUFFER_SIZE)

            # int TLPM_getRsrcName(void *vi, int device_index, char resourceName[])
            status = self.instrument_lib.TLPM_getRsrcName(None, i, resource_name)
            if status:
                raise ImportError("TLPM: Failed when trying to find connected devices - '{}'".format(self.get_error_message(status)))

            available_devices.append(resource_name.value.decode())

        return available_devices

    def _close(self):
        if self.instrument.value:
            # int TLPM_close(void *vi)
            status = self.instrument_lib.TLPM_close(self.instrument)
            if status:
                pass  # Don't do anything with this.

            self.instrument = ctypes.c_void_p(None)

    def get_power(self):
        power = ctypes.c_double(0)

        # int TLPM_measPower(void *vi, double *power);
        # use ctypes.pointer() to allow the emulator to modify this parameter
        status = self.instrument_lib.TLPM_measPower(self.instrument, ctypes.pointer(power))
        if status:
            raise RuntimeError("TLPM: Failed to get power - '{}'".format(self.get_error_message(status)))

        return power.value
