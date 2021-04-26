import ctypes
import glob
import os
import sys

from catkit.config import CONFIG_INI
from catkit.interfaces.PowerMeter import PowerMeter
import catkit.util

# Find TLPM_64.dll - the path to which needs to be added to PYTHONPATH.
# E.g. C:/Program Files/IVI Foundation/VISA/Win64/Bin/TLPM_64.dll.
TLPM_REQUIRED_LIB = "TLPM_64.dll"  # Yep, this is Windows specific.
TLPM_LIB_PATH = None

for path in sys.path:
    TLPM_LIB_PATH = glob.glob(os.path.join(path, TLPM_REQUIRED_LIB))

    if TLPM_LIB_PATH:
        break

if not TLPM_LIB_PATH:
    raise ImportError("TLPM: Failed to locate '{}' - add path to PYTHONPATH".format(TLPM_REQUIRED_LIB))

# Now load the found library.
try:
    TLPM_LIB = ctypes.cdll.LoadLibrary(TLPM_LIB_PATH[0])
except Exception as error:
    TLPM_LIB = None
    raise ImportError("TLPM: Failed to import '{}' library @ '{}'".format(TLPM_REQUIRED_LIB, TLPM_LIB_PATH)) from error


class TLPM(PowerMeter):
    instrument_lib = TLPM_LIB

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
        status = self.instrument_lib.TLPM_init(self.device_name.encode(), True, True, ctypes.byref(self.instrument))
        if status or self.instrument.value is None:
            raise OSError("TLPM: Failed to connect - '{}'".format(self.get_error_message(status)))

        return self.instrument

    @classmethod
    def get_error_message(cls, status_code):
        """Convert error status to error message."""
        error_message = ctypes.create_string_buffer(cls._BUFFER_SIZE)

        # int TLPM_errorMessage(void *vi, int statusCode, char description[])
        status = cls.instrument_lib.TLPM_errorMessage(None, status_code, error_message)
        if status:
            raise OSError("TLPM: Ironically failed to get error message - '{}'".format(cls.get_error_message(status)))

        return error_message.value.decode()

    @classmethod
    def create(cls, config_id):
        return cls(config_id=config_id, serial_number=CONFIG_INI.get(config_id, "serial_number"))

    @classmethod
    def find_all(cls):
        """Find all connected PM devices."""

        # First find the total number of connected PM devices.
        device_count = ctypes.c_int(0)

        # int TLPM_findRsrc(void *vi, int *resourceCount)
        status = cls.instrument_lib.TLPM_findRsrc(None, ctypes.byref(device_count))
        if status:
            raise ImportError("TLPM: Failed when trying to find connected devices - '{}'".format(cls.get_error_message(status)))

        # Then get their resource names.
        available_devices = []

        for i in range(device_count.value):
            resource_name = ctypes.create_string_buffer(cls._BUFFER_SIZE)

            # int TLPM_getRsrcName(void *vi, int device_index, char resourceName[])
            status = cls.instrument_lib.TLPM_getRsrcName(None, i, resource_name)
            if status:
                raise ImportError("TLPM: Failed when trying to find connected devices - '{}'".format(cls.get_error_message(status)))

            available_devices.append(buffer.value.decode())

        print(available_devices)

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
        status = self.instrument_lib.TLPM_measPower(self.instrument, ctypes.byref(power))
        if status:
            raise RuntimeError("TLPM: Failed to get power - '{}'".format(self.get_error_message(status)))

        return temp.value
