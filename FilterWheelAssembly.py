from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import logging

from serial import SerialException

from .thorlabs.ThorlabsFW102C import ThorlabsFW102C
from ..interfaces.Instrument import Instrument
from ..config import CONFIG_INI


class FilterWheelAssembly(Instrument):

    log = logging.getLogger(__name__)
    __FW1 = "filter_wheel_1"
    __FW2 = "filter_wheel_2"
    __fw_1_id = None
    __fw_2_id = None

    def initialize(self, *args, **kwargs):

        # Look up which filter wheels to use.
        self.__fw_1_id = CONFIG_INI.get("light_source_assembly", self.__FW1)
        self.__fw_2_id = CONFIG_INI.get("light_source_assembly", self.__FW2)

        # Initialize each filter wheel
        try:
            fw1_device = ThorlabsFW102C(self.__fw_1_id)
            fw2_device = ThorlabsFW102C(self.__fw_2_id)

            # Create a dictionary to hold both filter wheels, since it isn't just one instrument.
            instrument_dict = {self.__FW1: fw1_device, self.__FW2: fw2_device}
            return instrument_dict
        except SerialException as exp:
            print("One or both of the filter wheels aren't responding")
            raise exp

    def close(self):

        # Close filter wheels stored in the self.instrument as a dictionary.
        if self.instrument is not None:
            self.instrument[self.__FW1].close()
            self.instrument[self.__FW2].close()

    def set_filters(self, config_filter_name):

        # Look up filter combination.
        filter_names = CONFIG_INI.get(self.config_id, config_filter_name).split(",")

        # Resolve filter name to positions.
        pos1 = CONFIG_INI.getint(self.__fw_1_id, "filter_" + filter_names[0])
        pos2 = CONFIG_INI.getint(self.__fw_2_id, "filter_" + filter_names[1])

        # TODO: See if these can move in parallel.
        self.instrument[self.__FW1].set_position(pos1)
        self.instrument[self.__FW2].set_position(pos2)

    def get_filters(self):
        pos1 = self.instrument[self.__FW1].get_position()
        pos2 = self.instrument[self.__FW2].get_position()

        # Reverse lookup.
        filters_1 = {int(entry[1]): entry[0] for entry in CONFIG_INI.items("thorlabs_fw102c_1")
                   if entry[0].startswith("filter_")}
        filters_2 = {int(entry[1]): entry[0] for entry in CONFIG_INI.items("thorlabs_fw102c_2")
                   if entry[0].startswith("filter_")}

        return filters_1[pos1], filters_2[pos2]
