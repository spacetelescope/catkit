from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from multiprocessing.pool import ThreadPool

from builtins import *
import logging
from typing import NewType

from .thorlabs.ThorlabsFW102C import ThorlabsFW102C
from ..interfaces.Instrument import Instrument
from ..interfaces.FilterWheel import FilterWheel
from ..config import CONFIG_INI


class FilterWheelAssembly():

    log = logging.getLogger(__name__)

    def __init__(self, config_id, *args, **kwargs):

        # Look up which filter wheels to use.
        self.fw_1_id = CONFIG_INI.get("filter_wheel_assembly", "filter_wheel_1")
        self.fw_2_id = CONFIG_INI.get("filter_wheel_assembly", "filter_wheel_2")
        self.config_id = config_id

    def set_filters(self, config_filter_name):

        # Look up filter combination.
        filter_names = CONFIG_INI.get(self.config_id, config_filter_name).split(",")

        # Resolve filter name to positions.
        pos1 = CONFIG_INI.getint(self.fw_1_id, "filter_" + filter_names[0])
        pos2 = CONFIG_INI.getint(self.fw_2_id, "filter_" + filter_names[1])

        # TODO: See if these can move in parallel.
        with ThorlabsFW102C(self.fw_1_id) as fw1: #, ThorlabsFW102C(self.fw_2_id) as fw2:
            fw1.set_position(pos1)
            #fw2.set_position(pos2)

    def get_filters(self):
        with ThorlabsFW102C(self.fw_1_id) as fw1:# ThorlabsFW102C(self.fw_2_id) as fw2:
            pos1 = fw1.get_position()
            #pos2 = fw2.get_position()

            # Reverse lookup.
            filters_1 = {int(entry[1]): entry[0] for entry in CONFIG_INI.items("thorlabs_fw102c_1")
                       if entry[0].startswith("filter_")}
            filters_2 = {int(entry[1]): entry[0] for entry in CONFIG_INI.items("thorlabs_fw102c_1")
                       if entry[0].startswith("filter_")}

            return filters_1[pos1]#, filters_2[pos2]
