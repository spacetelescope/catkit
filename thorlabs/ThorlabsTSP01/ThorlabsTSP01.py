from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

import os
import subprocess


def get_temp_humidity():
    # Set up the paths.
    current_dir = os.path.dirname(os.path.realpath(__file__))
    full_path = os.path.join(current_dir, "bin", "thorlabs_sensor_cs.exe")

    # Create an args list and pass it into a subprocess.
    output = subprocess.check_output(full_path)
    # Remove curly brackets, spaces, and newlines.
    for remove_me in ["\r", "\n"]:
        output = output.replace(remove_me, "")

    values = output.split(" ")
    temp = float(values[0].split("=")[1])
    humidity = float(values[1].split("=")[1])
    return temp, humidity
