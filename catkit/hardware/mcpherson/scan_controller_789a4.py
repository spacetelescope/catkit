import enum
import functools
import re
import time
import warnings

from catkit.interfaces.Instrument import Instrument
import numpy as np
import pyvisa


# STUF model: 234/302
# STUF gratings: 355-107853-1 1200 g/mm concave corrected grating, Al+MgF2 coated, master holographic
#                355-110987-1 600 g/mm concave corrected grating, Al+MgF2 coated, master holographic

# For 234/302:
# 600 g/mm => 4nm/rev
# 1200 g/mm => 2nm/rev

DEFAULT_POLL = 0.8  # As documented in manual (seconds).
DEFAULT_POLL_TIMEOUT = 60  # This is not the comms timeout but that allowed for total polling duration (seconds).


class ASCIIControlCodes(enum.Enum):
    ENTER_CMD_MODE = " "  # AKA INIT.
    # INIT = ' '
    EXIT_CMD_MODE = chr(3)  # AKA RESET.
    # RESET = chr(3)  # Stops motion, sets counter to 0 (so man says, but doesn't), assumes idle state.
    SOFT_STOP = '@'  # Causes deacceleration to stop.
    DISABLE_HOME_SWITCH = "A0"
    ENABLE_HOME_SWITCH = "A8"
    ENABLE_HIGH_ACCURACY_HOMING = "A24"
    CLEAR = "C1"
    FIND_EDGE = 'F'
    # EXEC_INTERNAL_FUNC = 'G'
    START_VELOCITY = 'I'
    RAMP_SLOPE = 'K'
    PROGRAM_MODE = 'P'
    CONSTANT_VELOCITY_MOVE = 'M'
    SAVE = 'S'
    SCAN_SPEED = 'V'
    PAUSE = 'W'  # Wait/sleep.
    READ_PARAMS = 'X'
    GET_LIMIT_SWITCH_STATUS = ']'  # 0=no lim encountered, 32=home lim enc., 64=high lim enc., 128=low lim enc.
    SCAN_UP = '+'
    SCAN_DOWN = '-'
    GET_MOTION_STATUS = '^'  # 0=not moving, 1=moving, 2=high in const vel, 16=slewing ramping complete.


class LimitSwitchStatus(enum.Enum):
    # NOTE: It's possible to be both HOME & LOW as the HOME region is wide enough to include the LOW limit.
    NO_LIMIT = 0  # Not at any of the below. NOTE: Could be HOME but requires home switch to be enabled.
    HOME = 32  # NOTE: Requires home switch to be enabled.
    HIGH = 64
    LOW = 128


class MotionStatus(enum.Enum):
    STOPPED = 0
    MOVING = 1
    CONSTANT_VELOCITY = 2
    SLEWING_RAMPING_COMPLETE = 16


class Parameters(enum.Enum):
    RAMP_SLOPE = ASCIIControlCodes.RAMP_SLOPE.value
    START_VELOCITY = ASCIIControlCodes.START_VELOCITY.value
    SCAN_SPEED = ASCIIControlCodes.SCAN_SPEED.value


class McPherson789A4(Instrument):  # TODO: Write interface.

    instrument_lib = pyvisa

    _HAS_LIMIT_SWITCHES = False  # Use McPherson789A4WithLimitSwitches if True.

    BAUD_RATE = 9600
    DATA_BITS = 8
    STOP_BITS = pyvisa.constants.StopBits.one
    PARITY = pyvisa.constants.Parity.none
    FLOW_CONTROL = pyvisa.constants.ControlFlow.xon_xoff
    ENCODING = "ascii"
    QUERY_DELAY = 0.8  # s
    QUERY_TIMEOUT = 2000  # ms
    # HEADER_TIMEOUT = 20000  # ms
    WRITE_TERMINATION = '\r'
    READ_TERMINATION = "\r\n"

    MIN_SCAN_SPEED = 32
    MAX_SCAN_SPEED = 61440  # NOTE: Manual states 60000, but device's default is 61440.

    def initialize(self, visa_id, steps_per_rev=36000, timeout=None):
        self.visa_id = visa_id
        self.timeout = timeout
        self.instrument_lib = self.instrument_lib
        self.timeout = self.QUERY_TIMEOUT if timeout is None else timeout
        self._name = self.__class__.__name__

        self.steps_per_rev = steps_per_rev
        self.firmware_version = None

    def RESET(self):
        """ Reset device as if it were power cycled. """

        cmd = ASCIIControlCodes.EXIT_CMD_MODE
        self.instrument.write(cmd.value)
        time.sleep(2)

        try:
            # There's no response if calling this whilst in "command mode".
            mirrored_cmd = self.instrument.read('\r')  # For whatever reason, the read term is different from other commands.

            if ASCIIControlCodes(mirrored_cmd) is not cmd:
                raise RuntimeError(f"The device responded with a command different from that sent. Expected: '{cmd}' got '{mirrored_cmd}'")
        except pyvisa.VisaIOError:
            pass
        finally:
            # NOTE: There's a bug in pyvisa where the above actually changes the read_termination for all other reads.
            self.instrument.read_termination = self.READ_TERMINATION

    def INIT(self):
        # NOTE: Upon power up INIT will return the firmware version & a superfluous "#" (as a separate read).
        # However, any call after that returns only "#".

        resp = self.instrument.query(ASCIIControlCodes.ENTER_CMD_MODE.value).strip()

        if resp.startswith("v"):
            self.firmware_version = resp

            # Read the superfluous read associated with INIT.
            assert self.instrument.read().strip() == "#"
        elif resp == "#":
            pass
        else:
            raise RuntimeError(f"Unexpected response '{resp}'")

        time.sleep(1)

    def _open(self):

        rm = self.instrument_lib.ResourceManager('@py')

        # Open connection.
        self.instrument = rm.open_resource(self.visa_id,
                                           baud_rate=self.BAUD_RATE,
                                           data_bits=self.DATA_BITS,
                                           flow_control=self.FLOW_CONTROL,
                                           parity=self.PARITY,
                                           stop_bits=self.STOP_BITS,
                                           encoding=self.ENCODING,
                                           timeout=self.timeout,
                                           query_delay=self.QUERY_DELAY,
                                           write_termination=self.WRITE_TERMINATION,
                                           read_termination=self.READ_TERMINATION)
        time.sleep(1)

        # For a more consistent and repeatable operation we attempt
        # to RESET prior to sending INIT. Doing so is needed when considering that the device could be moving upon
        # connection and resetting will stop any movement.
        self.RESET()

        self.INIT()

        self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)
        return self.instrument

    def _close(self):
        if self.instrument:
            try:
                self.stop_motion()
                self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)
                self.RESET()
            finally:
                self.instrument.close()

    @staticmethod
    def parse_command(message):

        data = None

        if isinstance(message, ASCIIControlCodes):
            return message, data

        if not isinstance(message, str):
            raise TypeError(f"Message must either be of type str or '{ASCIIControlCodes.__name__}'")

        resp_list = message.split()
        resp_length = len(resp_list)

        cmd = resp_list[0]

        if resp_length == 1:
            data = None
        elif resp_length == 2:
            data = resp_list[1].strip()
        elif resp_length > 2:
            data = resp_list[1:]
        else:
            raise RuntimeError(f"Incorrect response length: {resp_length}")

        return cmd, data

    def read_params(self):
        cmd = ASCIIControlCodes.READ_PARAMS.value
        resp = self.instrument.query(cmd)

        if resp[0] != cmd:
            raise RuntimeError(f"The device responded with a command different from that sent. Expected: '{cmd}' got '{resp[0]}'")

        resp = resp[1:]
        resp = re.findall("[A-Z]+=[ ]*[0-9]+", resp)
        resp = [x.split("= ") for x in resp]
        resp = {Parameters(x[0]): int(x[1]) for x in resp}

        return resp

    def command(self, cmd, data=''):
        # Whilst it's possible to send a message like "30000" we'll restrict commanding to being explicit, i.e.,
        # "+30000". That way we can command-check.

        # Type check.
        cmd = ASCIIControlCodes(cmd)

        if not self._HAS_LIMIT_SWITCHES and cmd in (ASCIIControlCodes.ENABLE_HIGH_ACCURACY_HOMING,
                                                    ASCIIControlCodes.ENABLE_HOME_SWITCH,
                                                    ASCIIControlCodes.FIND_EDGE,
                                                    ASCIIControlCodes.GET_LIMIT_SWITCH_STATUS):
            raise NotImplementedError(f"This model does not support limit switches and the command: '{cmd}'")

        message_sent = f"{cmd.value}{data}"
        resp = self.instrument.query(message_sent)

        if cmd is ASCIIControlCodes.READ_PARAMS:
            cmd_resp, resp_data = resp[0], resp[1:]
        else:
            # Parse returned mirrored cmd from data (if any).
            cmd_resp, resp_data = (resp, '') if data else self.parse_command(resp)

        if message_sent != cmd_resp:
            # The controller replies back with the written cmd, failing to read this will cause communication to become out
            # of sync and thus cause future commands to fail to work (without raising an error).
            raise RuntimeError(f"The device responded with a command different from that sent. Expected: '{message_sent}' got '{cmd_resp}'")

        return resp_data

    def set_scan_speed(self, steps_per_second, rtol=0.02):
        steps_per_second = int(np.abs(steps_per_second))

        if self.MIN_SCAN_SPEED < steps_per_second > self.MAX_SCAN_SPEED:
            raise ValueError(f"{self.MIN_SCAN_SPEED} > SCAN_SPEED < {self.MAX_SCAN_SPEED} NOT {steps_per_second}.")

        self.command(ASCIIControlCodes.SCAN_SPEED, steps_per_second)

        # NOTE: The manual states that the actual scan speed may be different from that set.
        actual_scan_speed = self.read_params()[Parameters.SCAN_SPEED]

        if not np.isclose(actual_scan_speed, steps_per_second, rtol=rtol):
            warnings.warn(f"Set scan speed to {steps_per_second}, however, actual scan speed is {actual_scan_speed} (rtol={rtol}).")

        return actual_scan_speed

    def read_all(self, display=False):
        """ Helper func for when read/writes are out of sync - consume all waiting reads until buffer is empty. """
        try:
            while True:
                resp = self.instrument.read()
                if display:
                    print(resp)
        except pyvisa.VisaIOError:
            pass

    def read_all_bytes(self, display=False):
        """ Helper func for when read/writes are out of sync - consume all waiting reads until buffer is empty. """
        try:
            while True:
                resp = self.instrument.read_bytes(1)
                if display:
                    print(resp)
        except pyvisa.VisaIOError:
            pass

    def get_motion_status(self):
        """ This never returns MotionStatus.Moving, if it is moving is returns in which
            mode it is moving.
        """

        resp = np.int32(self.command(ASCIIControlCodes.GET_MOTION_STATUS))

        if resp & np.int32(MotionStatus.CONSTANT_VELOCITY.value):
            status = MotionStatus.CONSTANT_VELOCITY
        elif resp & np.int32(MotionStatus.SLEWING_RAMPING_COMPLETE.value):
            status = MotionStatus.SLEWING_RAMPING_COMPLETE
        elif resp & np.int32(MotionStatus.MOVING.value):
            status = MotionStatus.MOVING
        else:
            status = MotionStatus.STOPPED

        return status

    def is_moving(self):
        return self.get_motion_status() is not MotionStatus.STOPPED

    def poll_status(self, break_conditions, func, timeout=DEFAULT_POLL_TIMEOUT):
        """ Used to poll status whilst motor is in motion.
            NOTE: The poll delay := query delay.
        """
        status = None
        counter = 0
        while counter < timeout:
            status = func()
            if status in break_conditions:
                break

            # NOTE: There's no need to sleep between iterations as there is already a query delay effectively doing the
            # same thing.
            if timeout is not None and timeout > 0:
                counter += self.QUERY_DELAY

        if counter >= timeout:
            raise RuntimeError(f"Motor failed to complete operation within {timeout}s")

        return status

    def poll_motion(self, break_conditions, *args, **kwargs):
        return self.poll_status(break_conditions, self.get_motion_status, *args, **kwargs)

    def await_stop(self, *args, **kwargs):
        self.poll_motion((MotionStatus.STOPPED,), *args, **kwargs)

    def stop_motion(self, *args, **kwargs):
        """ Send command to stop motor then wait on confirmation that it has actually stopped. """
        self.command(ASCIIControlCodes.SOFT_STOP)
        self.await_stop(*args, **kwargs)

    def start_motion(self, steps_per_second):
        """ Constantly velocity motion until either hitting a (high|low) limit or motion explicitly stopped. """
        self.command(ASCIIControlCodes.CONSTANT_VELOCITY_MOVE, steps_per_second)

    def slew(self, steps, steps_per_second=None, reset_speed=True, wait=False):
        """ Move motor by a number of steps at a given speed. """
        cmd = ASCIIControlCodes.SCAN_UP if steps >= 0 else ASCIIControlCodes.SCAN_DOWN

        initial_scan_speed = actual_scan_speed = self.read_params()[Parameters.SCAN_SPEED]
        velocity_changed = False

        # Set speed.
        if steps_per_second is not None:
            if steps_per_second != actual_scan_speed:
                actual_scan_speed = self.set_scan_speed(steps_per_second)
                velocity_changed = True

        self.command(cmd, steps)

        if wait:
            self.await_stop()

        if reset_speed and velocity_changed:
            self.set_scan_speed(initial_scan_speed)

        return actual_scan_speed

    def home(self):
        raise NotImplementedError("This model does not support limit switches and therefore has no homing feature.")


class McPherson789A4WithLimitSwitches(McPherson789A4):
    _HAS_LIMIT_SWITCHES = True
    DEFAULT_HOMING_TIMEOUT = 60 * 5
    DEFAULT_HOMING_SPEED = 23000
    FAST_HOMING_SPEED = 3000000
    EDGE_DETECTION_SPEED = 1000

    def initialize(self, visa_id, steps_per_rev=36000, timeout=1):
        super().initialize(visa_id, steps_per_rev=steps_per_rev, timeout=timeout)

        self._home_on_startup = True
        if not self._home_on_startup:
            warnings.warn("It is strongly recommended to home on startup before proceeding with anything else! ")

    def _open(self, *args, **kwargs):
        self.instrument = super()._open(*args, **kwargs)

        if self._home_on_startup:
            self.home()

        return self.instrument

    def get_limit_status(self):
        resp = np.int32(self.command(ASCIIControlCodes.GET_LIMIT_SWITCH_STATUS))

        is_home = resp & np.int32(LimitSwitchStatus.HOME.value)

        if is_home:
            resp = resp - np.int32(LimitSwitchStatus.HOME.value)

        status = LimitSwitchStatus(resp)

        return status

    def poll_limit_status(self, break_conditions, *args, **kwargs):
        return self.poll_status(break_conditions, *args, **kwargs)

    def is_home(self, toggle_home_switch=True):
        # NOTE: If the home switch is disabled this will always return False.
        if toggle_home_switch:
            self.command(ASCIIControlCodes.ENABLE_HOME_SWITCH)

        try:
            resp = np.int32(self.command(ASCIIControlCodes.GET_LIMIT_SWITCH_STATUS))
            return bool(resp & np.int32(LimitSwitchStatus.HOME.value))
        finally:
            if toggle_home_switch:
                self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)

    def await_home(self, *args, **kwargs):
        poll_func = functools.partial(self.is_home, toggle_home_switch=False)
        self.poll_status((True,), poll_func, *args, **kwargs)

    def await_not_home(self, *args, **kwargs):
        poll_func = functools.partial(self.is_home, toggle_home_switch=False)
        self.poll_status((False,), poll_func, *args, **kwargs)

    def find_edge(self, steps_per_second, *args, **kwargs):
        # NOTE: When edge is found the position is just + of the home region such that self.is_home := False.

        if not self.is_home(toggle_home_switch=False):
            raise RuntimeError("Must be in home region to find edge.")

        # Enable "high accuracy" circuit.
        try:
            self.command(ASCIIControlCodes.ENABLE_HIGH_ACCURACY_HOMING)
            self.command(ASCIIControlCodes.FIND_EDGE, steps_per_second)
            self.await_stop(*args, **kwargs)
        finally:
            self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)

    def home(self, steps_per_second=DEFAULT_HOMING_SPEED, timeout=DEFAULT_HOMING_TIMEOUT, fast=False):
        """ This requires the use of limit switches.
            NOTE: This procedure is as outlined in the manual. The goal is to find the upper EDGE of the home region.
            NOTE: When edge is found the position is just + of the home region such that self.is_home := False.
            NOTE: The Home region is wide and includes the low limit.
            NOTE: For steps_per_second = 3e6 it takes ~210s to move from the low limit to the high limit and ~117s from
                  the high to home.
                  For steps_per_second = 23000 it takes ~470s to move from the low limit to the high limit and ~260s
                  from the high to home.
        """

        if fast:
            steps_per_second = self.FAST_HOMING_SPEED

        if steps_per_second > self.DEFAULT_HOMING_SPEED:
            warnings.warn(f"Uncalibrated backlash for speed: {steps_per_second} (>{self.DEFAULT_HOMING_SPEED}). Homing may fail.")

        print("Homing in progress... (this may take a while)")
        t0 = time.perf_counter()
        try:
            # Enable home circuit.
            self.command(ASCIIControlCodes.ENABLE_HOME_SWITCH)

            # Check whether already in home region.
            if self.is_home(toggle_home_switch=False):
                self.start_motion(steps_per_second=steps_per_second)
                self.await_not_home(timeout=timeout)
            else:
                self.start_motion(steps_per_second=-steps_per_second)
                self.await_home(timeout=timeout)

            # Soft stop.
            self.command(ASCIIControlCodes.SOFT_STOP)

            # The high accuracy edge detection circuit only moves in the + direction and, therefore, we need to far
            # enough below the edge of the home position to give it room to work. If it isn't, it will fail to find the
            # edge and timeout.

            # Move further down into home region (3 motor revs).
            self.slew(-self.steps_per_rev*3, wait=True)

            # Remove some backlash from the last move (2 motor revs).
            self.slew(self.steps_per_rev*2, wait=True)

            # Find edge of homing flag.
            self.find_edge(self.EDGE_DETECTION_SPEED, timeout=timeout)

            print(f"Homing complete. ({time.perf_counter() - t0})s")
        finally:
            self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)
