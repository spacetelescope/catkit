import ctypes
import glob
import os
import re
import sys
import warnings

from catkit.config import CONFIG_INI

# WARNING - this is neither functionally complete, nor robust against 32b vs 64b nor against model revision of TSP01.
# Some attempt has been made, however, I have been unable to load the Thorlabs TLTSP_<bit-length>.dll.

# The model revision is prefix is baked into the dll func names - this can be dealt with by implementing the following:
# func_name = "TSP01_LIB." + TSP01_LIB_PREFIX + func_to_call
# eval(func_name)() # the actual call
# However, not all func calls are identical, sigh...

# The current implementation of code exec upon import of this mod
# prevents both model revisions being used simultaneously.

# Find TLTSPB_64.dll - the path to which needs to be added to PYTHONPATH.
# E.g. C:/Program Files/IVI Foundation/VISA/Win64/Bin/TLTSPB_64.dll.
TSP01_REQUIRED_LIB = "TLTSPB_64.dll"  # Yep, this is Windows specific.
TSP01_LIB_PATH = None
for path in sys.path:
    TSP01_LIB_PATH = glob.glob(os.path.join(path, TSP01_REQUIRED_LIB))
    if TSP01_LIB_PATH:
        break
if not TSP01_LIB_PATH:
    raise ImportError("TSP01: Failed to locate '{}' - add path to PYTHONPATH".format(TSP01_REQUIRED_LIB))

# Now load the found library.
try:
    TSP01_LIB = ctypes.cdll.LoadLibrary(TSP01_LIB_PATH[0])
except Exception as error:
    TSP01_LIB = None
    raise ImportError("TSP01: Failed to import '{}' library @ '{}'".format(TSP01_REQUIRED_LIB, TSP01_LIB_PATH)) from error


class TSP01:
    # Don't use this class directly, instead use TSP01RevB.

    macro_definitions = {"TLTSP_BUFFER_SIZE": 256,
                         "TLTSP_TEMPER_CHANNEL_1": None,  # internal
                         "TLTSP_TEMPER_CHANNEL_2": None,  # external probe 1
                         "TLTSP_TEMPER_CHANNEL_3": None}  # external probe 2

    @classmethod
    def get_error_message(cls, status_code):
        """Convert error status to error message."""
        buffer_size = int(cls.macro_definitions["TLTSP_BUFFER_SIZE"])
        error_message = ctypes.create_string_buffer(buffer_size)
        # int TLTSPB_errorMessage(void * connection, int status_code, char * error_message)
        status = TSP01_LIB.TLTSPB_errorMessage(None, status_code, error_message)
        if status:
            raise OSError("TSP01: Ironically failed to get error message - '{}'".format(cls.get_error_message(status)))
        return error_message.value.decode()

    @classmethod
    def create(cls, config_id):
        serial_number = CONFIG_INI.get(config_id, "serial_number")
        return cls(serial_number)

    @classmethod
    def find_all(cls):
        """Find all connected TSP01 devices."""

        # First find the total number of connected TSP01 devices.
        device_count = ctypes.c_int(0)
        # int TLTSPB_findRsrc(void * connection, int * device_count)
        status = TSP01_LIB.TLTSPB_findRsrc(None, ctypes.byref(device_count))
        if status:
            raise ImportError("TSP01: Failed when trying to find connected devices - '{}'".format(cls.get_error_message(status)))

        # Then get their resource names.
        available_devices = []
        for i in range(device_count.value):
            # Create  a string buffer to contain result.
            buffer_size = int(cls.macro_definitions["TLTSP_BUFFER_SIZE"])
            buffer = ctypes.create_string_buffer(buffer_size)
            # int TLTSPB_getRsrcName(void * connection, int device_index, char * buffer)
            status = TSP01_LIB.TLTSPB_getRsrcName(None, i, buffer)
            if status:
                raise ImportError("TSP01: Failed when trying to find connected devices - '{}'".format(cls.get_error_message(status)))
            available_devices.append(buffer.value.decode())

        return available_devices

    def __init__(self, serial_number):
        self.connection = ctypes.c_void_p(None)
        self.serial_number = serial_number

        # Find the desired device resource name. This is not just the SN#.
        # NOTE: The revB call only finds revB devices.
        available_devices = self.find_all()
        self.device_name = [device for device in available_devices if self.serial_number in device]
        if not self.device_name:
            raise OSError("TSP01: device not found - SN# '{}'".format(self.serial_number))
        if len(self.device_name) > 1:
            raise OSError("TSP01: found multiple devices with the same SN# '{}'".format(self.serial_number))
        self.device_name = self.device_name[0]

        # int TLTSPB_init(char * device_name, bool id_query, bool reset_device, void ** connection)
        status = TSP01_LIB.TLTSPB_init(self.device_name.encode(), True, True, ctypes.byref(self.connection))
        if status or self.connection.value is None:
            raise OSError("TSP01: Failed to connect - '{}'".format(self.get_error_message(status)))

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()

    def __del__(self):
        self.close()

    def close(self):
        if self.connection.value:
            # int TLTSPB_close(void * connection)
            status = TSP01_LIB.TLTSPB_close(self.connection)
            if status:
                pass  # Don't do anything with this.
            self.connection = ctypes.c_void_p(None)

    def get_temp(self, channel):
        temp = ctypes.c_double(0)
        # int TLTSPB_getTemperatureData(void * connection, int channel, double * temp)
        status = TSP01_LIB.TLTSPB_measTemperature(self.connection, int(channel), ctypes.byref(temp))
        if status:
            raise RuntimeError("TSP01: Failed to get temperature - '{}'".format(self.get_error_message(status)))
        return temp.value

    def get_humidity(self):
        humidity = ctypes.c_double(0)
        # int TLTSPB_getHumidityData(void * connection, ?, double * humidity)
        status = TSP01_LIB.TLTSPB_measHumidity(self.connection, ctypes.byref(humidity))
        if status:
            raise RuntimeError("TSP01: Failed to get humidity - '{}'".format(self.get_error_message(status)))
        return humidity.value

    def get_temp_humidity(self):
        """Legacy func"""
        channel = self.macro_definitions["TLTSP_TEMPER_CHANNEL_2"]
        return self.get_temp(channel), self.get_humidity()


class TSP01RevA(TSP01):
    macro_definitions = TSP01.macro_definitions
    macro_definitions["TLTSP_TEMPER_CHANNEL_1"] = 1  # internal
    macro_definitions["TLTSP_TEMPER_CHANNEL_2"] = 2  # external probe 1
    macro_definitions["TLTSP_TEMPER_CHANNEL_3"] = 3  # external probe 2

    def __init__(self, serial_number):
        raise NotImplementedError()


class TSP01RevB(TSP01):
    macro_definitions = TSP01.macro_definitions
    macro_definitions["TLTSP_TEMPER_CHANNEL_1"] = 11  # internal
    macro_definitions["TLTSP_TEMPER_CHANNEL_2"] = 12  # external probe 1
    macro_definitions["TLTSP_TEMPER_CHANNEL_3"] = 13  # external probe 2
    pass
