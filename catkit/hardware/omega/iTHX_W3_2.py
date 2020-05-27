"""
Omega iTHX_W3_2 temperature humidity sensor.
https://www.omega.com/en-us/iiot-wireless/ithx-w3-series/p/ITHX-W3-2

Manual:
https://assets.omega.com/manuals/M4965.pdf

Commands:
*SRTC Read the temperature in C, celsius
*SRTF Read the temperature in F, fahrenheit
*SRH Read humidity
*SRD Read the dew point in C
*SRDF Read the dew point in F
*SRB Read the temperature in C and humidity
*SRBF Read the temperature in F and humidity
*SRYRST Reset Power on
"""

import re
import socket

import catkit.interfaces.TemperatureHumiditySensor


class TemperatureHumiditySensor(catkit.interfaces.TemperatureHumiditySensor.TemperatureHumiditySensor):
    instrument_lib = socket

    ADDRESS_FAMILY = instrument_lib.AF_INET
    SOCKET_KIND = instrument_lib.SOCK_STREAM
    BLOCK = True
    BUFFER_SIZE = 1024

    GET_TEMPERATURE_C = b"*SRTC\r"
    GET_HUMIDITY = b"*SRH\r"
    GET_TEMPERATURE_AND_HUMIDITY = b"*SRB\r"

    def initialize(self, host, port=2000, timeout=60):
        self.host = host
        self.port = port
        self.timeout = timeout

        if not self.BLOCK or not self.timeout:
            raise NotImplementedError(f"{self.config_id}: Async comm not supported.")

    def _open(self):
        connection = self.instrument_lib.socket(self.ADDRESS_FAMILY, self.SOCKET_KIND)
        connection.setblocking(self.BLOCK)
        connection.settimeout(self.timeout)
        connection.connect((self.host, self.port))

        return connection

    def _close(self):
        self.instrument.close()

    def _get_response(self):
        data = self.instrument.recv(self.BUFFER_SIZE)

        if data is None or not len(data):
            raise OSError(f"{self.config_id}: Unexpected error - no data received.")

        # Parse response. Example b"03.36\r" or b"03.36\r,45.2\r".
        data = re.findall("[\+\-0-9.]+", data.decode())

        # Convert to float.
        data = [float(item) for item in data]

        if len(data) == 1:
            return data[0]
        else:
            return tuple(data)

    def get_temp(self, channel=None):
        """ Measures and returns the temperature (Celsius). """
        if channel:
            raise NotImplementedError(f"{self.config_id}: Only single channel supported.")

        self.instrument.sendall(self.GET_TEMPERATURE_C)
        return self._get_response()

    def get_humidity(self):
        """ Measures and returns the relative humidity (%). """
        self.instrument.sendall(self.GET_HUMIDITY)
        return self._get_response()

    def get_temp_humidity(self):
        """ Measures and returns both the temperature (Celsius) and relative humidity (%). """
        self.instrument.sendall(self.GET_TEMPERATURE_AND_HUMIDITY)
        temp, humidity = self._get_response()
        return temp, humidity
