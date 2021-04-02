from catkit.interfaces.LaserSource import LaserSource


"""Interface for a laser source."""


class DummyLaserSource(LaserSource):
    def initialize(self, *args, **kwargs):
        return self

    def _close(self):
        self.log.info(f"Dummy laser '{self.config_id}' closed.")

    def _open(self):
        self.log.info(f"Dummy laser '{self.config_id}' opened.")
        return self

    def set_current(self, value, sleep=True):
        self.log.info(f"Dummy laser '{self.config_id}' set_current() being ignored.")

    def get_current(self):
        self.log.info(f"Dummy laser '{self.config_id}' get_current() returns None.")
        return None
