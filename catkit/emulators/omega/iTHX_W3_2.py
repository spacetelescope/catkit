import socket

import catkit.hardware.omega.iTHX_W3_2
from catkit.interfaces.Instrument import SimInstrument


class ITHXW32Emulator:

    NOMINAL_TEMPERATURE_C = 25.0
    NOMINAL_HUMIDITY = 20.0
    RETURN_FORMAT = "0{}\r"  # Concat delimiter := ","

    AF_INET = socket.AF_INET
    SOCK_STREAM = socket.SOCK_STREAM

    def __init__(self):
        self.command_cache = None

    def close(self):
        self.command_cache = None

    def connect(self, address):
        pass

    def recv(self, buffersize, flags=None):
        if self.command_cache == catkit.hardware.omega.iTHX_W3_2.TemperatureHumiditySensor.GET_TEMPERATURE_C:
            return self.RETURN_FORMAT.format(self.NOMINAL_TEMPERATURE_C).encode()
        elif self.command_cache == catkit.hardware.omega.iTHX_W3_2.TemperatureHumiditySensor.GET_HUMIDITY:
            return self.RETURN_FORMAT.format(self.NOMINAL_HUMIDITY).encode()
        elif self.command_cache == catkit.hardware.omega.iTHX_W3_2.TemperatureHumiditySensor.GET_TEMPERATURE_AND_HUMIDITY:
            return (self.RETURN_FORMAT.format(self.NOMINAL_TEMPERATURE_C) + "," + self.RETURN_FORMAT.format(self.NOMINAL_HUMIDITY)).encode()

    def sendall(self, data, flags=0):
        self.command_cache = data

    def setblocking(self, flag):
        pass

    def settimeout(self, flag):
        pass

    def socket(self, family=None, type=None, proto=0, fileno=None):
        return self


class TemperatureHumiditySensor(SimInstrument, catkit.hardware.omega.iTHX_W3_2.TemperatureHumiditySensor):
    instrument_lib = ITHXW32Emulator
