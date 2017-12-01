from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from .LaserSource import LaserSource


"""Interface for a laser source."""


class DummyLaserSource(LaserSource):

    def __init__(self, config_id, *args, **kwargs):
        self.config_id = config_id

    def initialize(self, *args, **kwargs):
        return None

    def close(self):
        print("Dummy Laser closed.")

    def set_current(self, value, sleep=True):
        print("Set Current being ignored.")

    def get_current(self):
        return None
