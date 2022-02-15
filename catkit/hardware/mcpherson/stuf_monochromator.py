# TODO: This doesn't belong in catkit.

import enum
import time
import warnings

from catkit.interfaces.Instrument import Instrument
from catkit.hardware.mcpherson.device_driver_747 import McPherson747
from catkit.hardware.mcpherson.scan_controller_789a4 import McPherson789A4WithLimitSwitches
from catkit.hardware.pyvisa_instrument import DEFAULT_POLL_TIMEOUT


# STUF model: 234/302
# STUF gratings: 355-107853-1 1200 g/mm concave corrected grating, Al+MgF2 coated, master holographic
#                355-110987-1 600 g/mm concave corrected grating, Al+MgF2 coated, master holographic

# For 234/302:
# 600 g/mm => 4nm/rev
# 1200 g/mm => 2nm/rev


class Grating(enum.Enum):
    def __init__(self, g_per_mm, nm_rev, position):
        self.g_per_mm = g_per_mm
        self.nm_rev = nm_rev
        self.position = position

    @classmethod
    def _missing_(cls, value):
        for item in cls:
            if value in (item.g_per_mm, item.position):  # Luckily these are unique.
                return item

    # TODO: Check correctness of positions.
    A = (6000, 4, 1)
    B = (1200, 2, 2)


class StufMonochromator(Instrument):

    GRATING_DEVICE_NUMBER = 3

    def initialize(self, gratings, kwargs_747, kwargs_789a4):
        self.gratings = gratings

        self.grating_controller = McPherson747(kwargs_747)
        self.scan_controller = McPherson789A4WithLimitSwitches(kwargs_789a4)

        self._current_grating = None

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
            self._current_grating = None

    @property
    def grating(self):
        self._current_grating = Grating(self.grating_controller.get_current_position(self.GRATING_DEVICE_NUMBER))

    @grating.setter
    def grating(self, grating):
        grating = Grating(grating)
        try:
            self.grating_controller.set_current_position(self.GRATING_DEVICE_NUMBER, grating.position, wait=True)
        except Exception:
            self._current_grating = None
            raise
        else:
            # The above selection will raise if the resultant grating is not as desired. We therefore don't need to
            # explicitly query it again.
            self._current_grating = grating

    def toggle_grating(self):
        """ Toggle to the other grating. """

        initial_grating = self.grating()
        grating = Grating.A if initial_grating is Grating.B else Grating.B
        self.grating = grating

    def scan(self, nm, nm_per_second, wait=False):
        """  Scan `nm` distance with velocity `nm_per_second`.

        :param nm: int, float - The number of nm to move by.
        :param nm_per_second: int, float - Requested scan velocity. If `None` it uses the velocity set on the
                                           device. NOTE: The speed that the motor moves at might not be exactly
                                           that requested so check return value for actual motor velocity.
        :param wait: bool (optional) - Whether to wait for motion to have stopped before returning from this func.

        :return: float - nm_per_second, actual motor velocity.
        """

        steps_per_nm = self.scan_controller.steps_per_rev / self.current_grating.nm_rev
        steps = nm * steps_per_nm
        steps_per_second = nm_per_second * steps_per_nm

        duration = nm / nm_per_second * 1.5 if wait else DEFAULT_POLL_TIMEOUT

        t0 = time.perf_counter()
        actual_velocity = self.scan_controller.slew(steps=steps,
                                                    steps_per_second=steps_per_second,
                                                    reset_speed=True,
                                                    timeout=duration,
                                                    wait=wait)

        if wait:
            t1 = time.perf_counter()
            tol = 0.1
            if t1 - t0 > duration * (1 + tol):
                warnings.warn(f"Scan duration >={tol*100:.2f}% longer than expected ({t1 - t0 - duration:.2f}s > {duration:.2f}s).")

        return actual_velocity / steps_per_nm

    def is_moving(self):
        """ Is the monochromator moving?

        :return: bool
        """
        return self.scan_controller.is_moving() or self.grating_controller.is_moving()

    def await_stop(self, timeout=DEFAULT_POLL_TIMEOUT):
        """ Wait for the monochromator to stop moving.

        :param timeout: int, float (optional) - Raise TimeoutError if the devices hasn't stopped within timeout seconds.
                                                0, None, & negative values => infinite timeout.
                                                NOTE: Time elapsed may be double that given.
        """

        self.scan_controller.await_stop(timeout=timeout)
        self.grating_controller.await_stop(timeout=timeout)

    def start_continuous_scan(self, nm_per_second):
        """ Start continuous scanning at constant velocity until either hitting a high|low limit or motion is explicitly
        stopped.

        :param nm_per_second: int - Scan speed in nm per second.
        """

        steps_per_nm = self.scan_controller.steps_per_rev / self.current_grating.nm_rev
        steps_per_second = nm_per_second * steps_per_nm
        self.scan_controller.start_motion(steps_per_second)

    def stop_scan(self, timeout=DEFAULT_POLL_TIMEOUT):
        """ Stop scanning then wait on confirmation that it has actually stopped.

        See self.await_stop() for timeout semantics.
        """
        self.scan_controller.stop_motion(timeout=timeout, wait=True)
