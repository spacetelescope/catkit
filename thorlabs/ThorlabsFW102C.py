from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import logging
import visa
import platform
from ...config import CONFIG_INI
from pyvisa import constants
import time

from .. import testbed_state
from ...interfaces.FilterWheel import FilterWheel


class ThorlabsFW102C(FilterWheel):
    """Abstract base class for filter wheels."""

    log = logging.getLogger(__name__)

    def initialize(self, *args, **kwargs):

        rm = visa.ResourceManager('@py')

        # Determine the os, and load the correct filter ID from the ini file.
        if platform.system().lower() == "darwin":
            visa_id = CONFIG_INI.get(self.config_id, "mac_resource_name")
        elif platform.system().lower() == "windows":
            visa_id = CONFIG_INI.get(self.config_id, "windows_resource_name")
        else:
            visa_id = CONFIG_INI.get(self.config_id, "windows_resource_name")

        # These values took a while to figure out, careful changing them.
        return rm.open_resource(visa_id,
                                baud_rate=115200,
                                data_bits=8,
                                write_termination='\r',
                                read_termination='\r')

    def close(self):
        self.instrument.close()

    def get_position(self):
        out = self.instrument.write("pos?")

        if out[1] == constants.StatusCode.success:

            # First read the echo to clear the buffer.
            self.instrument.read()

            # Now read the filter position, and convert to an integer.
            return int(self.instrument.read())
        else:
            raise Exception("Filter wheel " + self.config_id + " returned an unexpected response: " + out[1])

    def set_position(self, new_position):
        command = "pos=" + str(new_position)
        out = self.instrument.write(command)

        if out[1] == constants.StatusCode.success:
            self.instrument.read()

            # Update testbed state.
            testbed_state.filter_wheels[self.config_id] = new_position
            time.sleep(3)
        else:
            raise Exception("Filter wheel " + self.config_id + " returned an unexpected response: " + out[1])

    def ask(self, write_string):
        self.instrument.write(write_string)

    def read(self):
        return self.instrument.read()

    def flush(self):
        print(self.instrument.read_bytes(1))
