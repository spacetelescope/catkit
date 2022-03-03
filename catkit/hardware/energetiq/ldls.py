import enum
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
                   sleep_interval=1):
        self.address = address
        self.sleep_interval=sleep_interval

    def _open(self):
        instrument = pigpio.pi(host=self.address[0], port=self.address[1])

        if instrument.connected:
            self.instrument = instrument
        else:
            RuntimeError("Failed to connect.")

        self.initialize_all_pins()
        return self.instrument

    def _close(self):
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
        self.instrument.write(Pin.lamp_operate.value, state)
        time.sleep(self.sleep_interval)

    def set_interlock(self, state):
        self.instrument.write(Pin.interlock.value, state)
        time.sleep(self.sleep_interval)

    def initialize_all_pins(self):
        for pin in Pin:
            if pin in (22, 27):
                self.instrument.set_mode(pin.value, self.instrument_lib.INPUT)
            else:
                self.instrument.set_mode(pin.value, self.instrument_lib.OUTPUT)


SharedMemoryManager.register("LDLS", callable=LDLS)
