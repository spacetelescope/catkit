from catkit.interfaces.LaserSource import LaserSource


"""Interface for a laser source."""


class DummyLaserSource(LaserSource):
    def initialize(self, *args, **kwargs):
        return self

    def _close(self):
        self.log.info("Dummy Laser closed.")

    def _open(self):
        return self

    def set_current(self, value, sleep=True):
        self.log.info("Set Current being ignored.")

    def get_current(self):
        return None
