import enum
from multiprocess.managers import NamespaceProxy
import os
import time

from catkit.interfaces.Instrument import Instrument
from catkit.multiprocessing import SharedMemoryManager
import pigpio


class Pin(enum.IntEnum):
    lamp_state = 6
    laser_state = 5
    lamp_operate = 22
    controller_fault = 24
    lamp_fault = 25
    interlock = 27


class LDLS(Instrument):

    instrument_lib = pigpio

    def initialize(self, address=(os.getenv("PIGPIO_ADDR", 'localhost'), os.getenv("PIGPIO_PORT", 8888)),
                   sleep_interval=2, laser_timeout=5*60, power_off_on_exit=False):
        self.address = address
        self.sleep_interval=sleep_interval
        self.laser_timeout = laser_timeout
        self.power_off_on_exit = power_off_on_exit

    def _open(self):
        instrument = pigpio.pi(host=self.address[0], port=self.address[1])

        if instrument.connected:
            self.instrument = instrument
        else:
            RuntimeError("Failed to connect.")

        self.initialize_all_pins()

        self.remove_fault()

        return self.instrument

    def _close(self):
        if self.power_off_on_exit:
            self.source_off(wait=False)
        self.instrument.stop()

    def get_status(self):
        # NOTE: Returns raw values where 0 doesn't always := False!

        status = {Pin.lamp_state: None,
                  Pin.laser_state: None,
                  Pin.interlock: None,
                  Pin.controller_fault: None,
                  Pin.lamp_fault: None}
        for pin in status:
            status[pin] = self.instrument.read(pin.value)
        return status

    def is_laser_on(self):
        return not bool(self.instrument.read(Pin.laser_state.value))

    def is_lamp_on(self):
        return not bool(self.instrument.read(Pin.lamp_state.value))

    def lamp_fault_detected(self):
        return bool(self.instrument.read(Pin.lamp_fault.value))

    def is_interlock_on(self):
        return bool(self.instrument.read(Pin.interlock.value))

    def controller_fault_detected(self):
        return bool(self.instrument.read(Pin.controller_fault.value))

    def set_lamp(self, state):
        state = int(state)
        self.instrument.write(Pin.lamp_operate.value, state)
        time.sleep(self.sleep_interval)

    def set_interlock(self, state):
        state = int(state)
        self.instrument.write(Pin.interlock.value, state)
        time.sleep(self.sleep_interval)

    def initialize_all_pins(self):
        for pin in Pin:
            if pin in (22, 27):
                self.instrument.set_mode(pin.value, self.instrument_lib.INPUT)
            else:
                self.instrument.set_mode(pin.value, self.instrument_lib.OUTPUT)

    def remove_fault(self):
        if not self.controller_fault_detected() and not self.lamp_fault_detected():
            return

        self.set_interlock(True)
        assert self.is_interlock_on()

        # Toggle operate to remove ctrl fault.
        self.set_lamp(True)
        self.set_lamp(False)

        if self.controller_fault_detected():
            raise RuntimeError("Toggling lamp failed to remove controller fault.")

    def source_on(self, wait=True):
        """ Turn on the laser and wait for it to excite the lamp. """

        self.remove_fault()

        self.set_interlock(True)
        self.set_lamp(True)
        time.sleep(5)  # It takes a while for the laser to report as on.

        if not self.is_laser_on() or self.lamp_fault_detected() or self.controller_fault_detected():
            raise RuntimeError("Fault detected.")

        if wait:
            print("Waiting for lamp to emit (this will take a couple of minutes)...")
            counter = 0
            while counter < self.laser_timeout:
                if self.is_lamp_on():
                    print(f"Lamp on. ({counter}s).")
                    return
                time.sleep(1)
                counter += 1

            try:
                raise TimeoutError(f"The laser took longer than {self.laser_timeout} to warm up.")
            finally:
                if self.lamp_fault_detected():
                    raise RuntimeError("Lamp fault detected.")

    def source_off(self, wait=True):
        """ This will instantly turn the laser off which will result in the lamp being off. """

        self.remove_fault()

        self.set_lamp(False)

        if wait:
            counter = 0
            while counter < self.laser_timeout:
                if not self.is_lamp_on() and not self.is_lamp_on():
                    return
                time.sleep(1)
                counter += 1

            try:
                raise TimeoutError(f"The laser took longer than {self.laser_timeout} to turn off.")
            finally:
                if self.controller_fault_detected():
                    raise RuntimeError("Controller fault detected.")

    def operate_source(self, on=True):
        if on:
            return self.source_on(wait=True)
        else:
            return self.source_off(wait=False)

    class Proxy(NamespaceProxy):
        _exposed_ = ("__enter__", "__exit__", "source_on", "source_off")
        _method_to_typeid_ = {"__enter__": "LDLSProxy"}

        def __enter__(self):
            return self._callmethod("__enter__")

        def __exit__(self, *args, **kwargs):
            return self._callmethod("__exit__", args=args, kwds=kwargs)

        def source_on(self, *args, **kwargs):
            return self._callmethod("source_on", args=args, kwds=kwargs)

        def source_off(self, *args, **kwargs):
            return self._callmethod("source_off", args=args, kwds=kwargs)


SharedMemoryManager.register("LDLS", callable=LDLS, proxytype=LDLS.Proxy, create_method=True)
SharedMemoryManager.register("LDLSProxy", callable=LDLS.Proxy, create_method=False)
