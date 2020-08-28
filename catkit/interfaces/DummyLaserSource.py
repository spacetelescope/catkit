import logging

from catkit.interfaces.LaserSource import LaserSource


"""Interface for a laser source."""


class DummyLaserSource(LaserSource):
    log = logging.getLogger(__name__)

    def initialize(self, *args, **kwargs):
        return None

    def close(self):
        self.log.info("Dummy Laser closed.")

    def set_current(self, value, sleep=True):
        self.log.info("Set Current being ignored.")

    def get_current(self):
        return None
