from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import os
import subprocess
from ...config import CONFIG_INI

class ThorlabsTSP01():
    def __init__(self, config_id):
        self.config_id = config_id
        self.serial_number = CONFIG_INI.get(self.config_id, "serial_number")

    def get_temp_humidity(self):
        """
        Connects to Thorlabs TSP01 sensor and reads the external temperature and humidity.
        :param: The id of the thorlabs TSP01 in the config.ini file (ex: thorlabs_tsp01_1)
        :return: Temperature, Humidity as floats. 
        """
        # Set up the paths.s
        current_dir = os.path.dirname(os.path.realpath(__file__))
        full_path = os.path.join(current_dir,
                                 "tsp01_resources",
                                 "src", "thorlabs_sensor_cs", "bin", "Release", "thorlabs_sensor_cs.exe " + self.serial_number)
        output = subprocess.check_output(full_path)

        if 'error' in output:
            raise RuntimeError(output)
        # Remove newlines.
        for remove_me in ["\r", "\n"]:
            output = output.replace(remove_me, "")

        values = output.split(" ")
        if len(values) < 2:
            raise RuntimeError("Expected at least 2 values returned in sensor output; instead got '{}' ".format(output))
        temp = float(values[0].split("=")[1])
        humidity = float(values[1].split("=")[1])
        return temp, humidity
