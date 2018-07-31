from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import logging
import visa
from pyvisa.constants import StatusCode

from ...interfaces.FilterWheel import FilterWheel


class ThorlabsFW102C(FilterWheel):
    """Abstract base class for filter wheels."""

    log = logging.getLogger(__name__)

    def initialize(self, *args, **kwargs):

        rm = visa.ResourceManager('@py')
        # Windows ASRLCOM3::INSTR
        return rm.open_resource('ASRL/dev/cu.usbserial-TP01517280-7417::INSTR',
                                           baud_rate=115200,
                                           data_bits=8,
                                           write_termination='\r',
                                           read_termination='\r')

    def close(self):
        self.instrument.close()

    def get_position(self):
        out = self.instrument.write("pos?")

        if out[1] == StatusCode.success:

            # First read the echo to clear the buffer.
            self.instrument.read()

            # Now read the filter position, and convert to an integer.
            return int(self.instrument.read())
        else:
            raise Exception("Filter wheel " + self.config_id + " returned an unexpected response: " + out[1])

    def set_position(self, new_position):
        string1 = "pos=1"
        string2 = unicode("pos=" + str(new_position))
        out = self.instrument.write(string2)

        if out[1] == StatusCode.success:
            self.instrument.read()
        else:
            raise Exception("Filter wheel " + self.config_id + " returned an unexpected response: " + out[1])
