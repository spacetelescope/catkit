# TODO: This doesn't belong in catkit.

import enum
import time
import warnings

from catkit.interfaces.Instrument import Instrument
from catkit.hardware.mcpherson.device_driver_747 import McPherson747
from catkit.hardware.mcpherson.scan_controller_789a4 import McPherson789A4WithLimitSwitches


class Grating(enum.Enum):
    def __init__(self, g_per_mm, nm_rev, position):
        self.g_per_mm = g_per_mm
        self.nm_rev = nm_rev
        self.position = position

    @classmethod
    def _missing_(cls, value):
        for item in cls:
            # NOTE: As is, this requires members to be unique in g_per_mm.
            if value == item.g_per_mm:
                return item

    A = (6000, 4, 1)
    B = (1200, 2, 2)


class StufMonochromator(Instrument):

    def initialize(self, gratings, kwargs_747, kwargs_789a4):
        self.gratings = gratings

        self.grating_controller = McPherson747(kwargs_747)
        self.scan_controller = McPherson789A4WithLimitSwitches(kwargs_789a4)

        self.current_grating = None

    def manage_controllers(self):
        with self.grating_controller:
            with self.scan_controller:
                yield

    def _open(self):
        self.manage_controllers()
        return self

    def _close(self):
        try:
            self.manage_controllers()
        finally:
            self.current_grating = None

    def select_grating(self, grating):
        grating = Grating(grating)
        try:
            self.grating_controller.move(grating.position)
        except Exception:
            self.current_grating = None
            raise
        else:
            self.current_grating = grating

    def scan(self, nm, nm_per_second, wait=False):
        steps_per_nm = self.scan_controller.steps_per_rev / self.current_grating.nm_rev
        steps = nm * steps_per_nm
        steps_per_second = nm_per_second * steps_per_nm

        t0 = time.perf_counter()
        self.scan_controller.slew(steps=steps, steps_per_second=steps_per_second)

        if wait:
            duration = nm / nm_per_second
            self.scan_controller.await_stop(timeout=duration * 1.5)
            t1 = time.perf_counter()

            tol = 0.1
            if t1 - t0 > duration * (1 + tol):
                warnings.warn(f"Scan duration {tol*100:.2f}% longer than expected ({t1 - t0 - duration:.2f}s > {duration:.2f}s).")

    def is_moving(self):
        return self.scan_controller.is_moving() or self.grating_controller.is_moving()

    def await_stop(self, *args, **kwargs):
        # NOTE: This does not need to wait on the grating controller as the grating controller's functionality always
        # implicitly waits.
        return self.scan_controller.await_stop(*args, **kwargs)
