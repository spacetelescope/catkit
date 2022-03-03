import enum
import os

from catkit.interfaces.Instrument import Instrument
from catkit.multiprocessing import SharedMemoryManager
import pigpio


class GPIO(enum.IntEnum):
    lamp_state = 6
    laser_state = 5
    lamp_operate = 22
    controller_fault = 24
    lamp_fault = 25
    interlock = 27


# TODO: Do all "sets" require a sleep before returning?
# TODO: Should all writes be checked with a subsequent read? (May need a query/sleep delay?)

class LDLS(Instrument):

    instrument_lib = pigpio

    def initialize(self, address=(os.getenv("PIGPIO_ADDR", 'localhost'),
                                  os.getenv("PIGPIO_PORT", 8888))):
        self.address = address

    def _open(self):
        instrument = pigpio.pi(host=self.address[0], port=self.address[1])

        if instrument.connected:
            self.instrument = instrument
        else:
            RuntimeError("Failed to connect.")

        self.initialize_gpio()
        return self.instrument

    def _close(self):
        self.instrument.stop()

    def get_status(self):
        # NOTE: Returns raw values where 0 doesn't always := False!

        status = {GPIO.lamp_state: None,
                  GPIO.laser_state: None,
                  GPIO.interlock: None,
                  GPIO.controller_fault: None,
                  GPIO.lamp_fault: None}
        for pin in status:
            status[pin] = self.instrument.read(pin.value)
        return status

    def is_laser_on(self):
        return not bool(self.instrument.read(GPIO.laser_state.value))

    def is_lamp_on(self):
        return not bool(self.instrument.read(GPIO.lamp_state.value))

    def lamp_fault_detected(self):
        return bool(self.instrument.read(GPIO.lamp_fault.value))

    def is_interlock_on(self):
        return bool(self.instrument.read(GPIO.interlock.value))

    def controller_fault_detected(self):
        return bool(self.instrument.read(GPIO.controller_fault.value))

    def set_lamp(self, state):
        self.instrument.write(GPIO.lamp_operate.value, state)

    def set_interlock(self, state):
        self.instrument.write(GPIO.interlock.value, state)

    def initialize_gpio(self):
        for pin in GPIO:
            if pin in (22, 27):
                self.instrument.set_mode(pin.value, self.instrument_lib.INPUT)
            else:
                self.instrument.set_mode(pin.value, self.instrument_lib.OUTPUT)


SharedMemoryManager.register("LDLS", callable=LDLS)
