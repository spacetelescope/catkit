import enum
import functools
import re
import time
import warnings

from catkit.hardware.pyvisa_instrument import CommandEchoError, DEFAULT_POLL_TIMEOUT, PyVisaInstrument
import catkit.util
import numpy as np
import pyvisa


DEFAULT_POLL = 0.8  # As documented in manual (seconds).


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
    INBETWEEN = 0  # Not at any of the below. NOTE: Could be HOME but requires home switch to be enabled.
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


class McPherson789A4(PyVisaInstrument):
    """ Base class for Mcpherson 789A-4 scan controller.
        NOTE: This class has no homing functionality, for that use McPherson789A4WithLimitSwitches.
    """

    _HAS_LIMIT_SWITCHES = False  # Use McPherson789A4WithLimitSwitches if True.

    BAUD_RATE = 9600
    DATA_BITS = 8
    STOP_BITS = pyvisa.constants.StopBits.one
    PARITY = pyvisa.constants.Parity.none
    FLOW_CONTROL = pyvisa.constants.ControlFlow.xon_xoff
    ENCODING = "ascii"
    QUERY_DELAY = 0.8  # s
    QUERY_TIMEOUT = 2000  # ms
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

    def reset(self):
        """ Reset device as if it were power cycled. """

        # NOTE: We don't use self.command() here due to the response being dependent on existing state.

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

    def init(self):
        """ Initialize device ready for excepting commands. """

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
        """ Open connection to the device. This is called by Instrument.__enter__() such that the device is context
            managed.
        """

        # rm = self.instrument_lib.ResourceManager('@py')

        # Open connection.
        self.instrument = self.instrument_lib.open_resource(self.visa_id,
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
        self.reset()

        self.init()

        self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)
        return self.instrument

    def _close(self):
        if self.instrument:
            try:
                self.stop_motion()
                self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)
                self.reset()
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
        """ Read parameters ramp slope (K), initial velocity (I), & scan speed (V).
            Returns a dict of Parameter enums members.
        """

        cmd = ASCIIControlCodes.READ_PARAMS.value
        resp = self.instrument.query(cmd)

        if resp[0] != cmd:
            raise CommandEchoError(cmd, resp[0])

        resp = resp[1:]  # The first char is the mirrored cmd 'X' so remove it from data before parsing.
        resp = re.findall("[A-Z]+=[ ]*[0-9]+", resp)  # Example: resp = "K= 50 I= 1000 V= 61440"
        resp = [x.split("= ") for x in resp]
        resp = {Parameters(x[0]): int(x[1]) for x in resp}

        return resp

    def command(self, cmd, data=''):
        """ Send command to device. Sent in the format: f"{ASCIIControlCodes(cmd).value}{data}".

        :param cmd: ASCIIControlCodes, str - The command to send to the device.
        :param data: Any type with a __str__ method. (optional)
        """

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
        try:
            resp = self.instrument.query(message_sent)
        except Exception as error:
            raise RuntimeError(f"The command: '{cmd}' failed. (data: '{data}')") from error

        if cmd is ASCIIControlCodes.READ_PARAMS:
            cmd_resp, resp_data = resp[0], resp[1:]
        else:
            # Parse returned mirrored cmd from data (if any).
            cmd_resp, resp_data = (resp, '') if data else self.parse_command(resp)

        if message_sent != cmd_resp:
            # The controller replies back with the written cmd, failing to read this will cause communication to become out
            # of sync and thus cause future commands to fail to work (without raising an error).
            raise CommandEchoError(message_sent, cmd_resp)

        return resp_data

    def set_slew_speed(self, steps_per_second, rtol=0.02, throw=False):
        """ Set the speed used by self.slew().

        :param steps_per_second: int - velocity value to set.
        :param rtol: float - The motor velocity doesn't have integer fidelity and thus the motor velocity used may not
                             be exactly that requested. rtol is the relative tolerance used to compare the actual
                             velocity to that requested. If not within tolerance it will raise a warning, or raise an
                             exception if throw is True.
        :param throw: bool (optional) - If set velocity is not within tolerance raise an exception instead or a warning.

        :return: int - The actual velocity with which the motor will slew.
        """

        steps_per_second = int(np.abs(steps_per_second))

        if self.MIN_SCAN_SPEED < steps_per_second > self.MAX_SCAN_SPEED:
            raise ValueError(f"{self.MIN_SCAN_SPEED} > SCAN_SPEED < {self.MAX_SCAN_SPEED} NOT {steps_per_second} (steps/s).")

        self.command(ASCIIControlCodes.SCAN_SPEED, steps_per_second)

        # NOTE: The manual states that the actual scan speed may be different from that set.
        actual_scan_speed = self.read_params()[Parameters.SCAN_SPEED]

        if not np.isclose(actual_scan_speed, steps_per_second, rtol=rtol):
            msg = f"Set scan speed to {steps_per_second}, however, actual scan speed is {actual_scan_speed} (rtol={rtol})."
            if throw:
                raise ValueError(msg)
            else:
                warnings.warn(msg)

        return actual_scan_speed

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
        """ Returns bool. """
        return self.get_motion_status() is not MotionStatus.STOPPED

    def poll_motion(self, break_conditions, *args, **kwargs):
        """ Poll device for motion status. See catkit.util.poll_status() for more info. """
        return catkit.util.poll_status(break_conditions, self.get_motion_status, *args, **kwargs)

    def await_stop(self, timeout=DEFAULT_POLL_TIMEOUT):
        """ Wait for device to indicate it has stopped moving. Poll the device at intervals of self.QUERY_DELAY until
        it has stopped.

        :param timeout: int, float (optional) - Raise TimeoutError if the devices hasn't stopped within timeout seconds.
                                                0, None, & negative values => infinite timeout.
        """
        self.poll_motion((MotionStatus.STOPPED,), timeout=timeout)

    def stop_motion(self, timeout=DEFAULT_POLL_TIMEOUT, wait=True):
        """ Send command to stop motor then (optionally) wait on confirmation that it has actually stopped.
        See self.await_stop() for timeout semantics.

        NOTE: If using this interactively after interrupting running control, you should call self.read_all_bytes()
              before and after calling this func to prevent errors caused by the interrupt, e.g., orphaned responses on
              the device.
        """

        self.command(ASCIIControlCodes.SOFT_STOP)
        if wait:
            self.await_stop(timeout=timeout)

    def start_motion(self, steps_per_second):
        """ Move motor at constant velocity until either hitting a high|low limit or motion is explicitly stopped.

        :param steps_per_second: int - Move motor with velocity := steps_per_second.
        """
        self.command(ASCIIControlCodes.CONSTANT_VELOCITY_MOVE, steps_per_second)

    def slew(self, steps, steps_per_second=None, reset_speed=True, wait=False, timeout=DEFAULT_POLL_TIMEOUT):
        """ Move motor by a number of steps at a given speed.

        :param: steps: int - The number of steps to move by. + values move "up", - values move "down". NOTE: May not
                             move by full amount if motor encounters a (high|low) limit stop.
        :param steps_per_second: int (optional) - Requested motor velocity. If `None` it uses the velocity set on the
                                                  device. NOTE: The speed that the motor moves at might not be exactly
                                                  that requested so check return value for actual motor velocity.
        :param reset_speed: bool (optional) - To slew at the requested velocity (if given) the velocity must be set on
                                              the device. This value will be persistent. If False allow value to persist
                                              otherwise reset velocity to that prior to calling this func.
                                              NOTE: Only available if wait is True.
        :param wait: bool (optional) - Whether to wait for motion to have stopped before returning from this func.
        :param timeout: int, float (optional) - Raise TimeoutError if the devices hasn't stopped within timeout
                                                seconds (only applies when `wait` is True.
                                                0, None, & negative values => infinite timeout.

        :return: int - steps_per_second, actual motor velocity.
        """

        if not isinstance(steps, int):
            raise TypeError(f"steps must be of type int not {type(steps)}.")

        if steps_per_second and not isinstance(steps_per_second, int):
            raise TypeError(f"steps_per_second must be of type int not {type(steps_per_second)}.")

        cmd = ASCIIControlCodes.SCAN_UP if steps >= 0 else ASCIIControlCodes.SCAN_DOWN

        initial_scan_speed = actual_scan_speed = self.read_params()[Parameters.SCAN_SPEED]
        velocity_changed = False

        # Set speed.
        if steps_per_second is not None and steps_per_second != actual_scan_speed:
                actual_scan_speed = self.set_slew_speed(steps_per_second)
                velocity_changed = True

        self.command(cmd, steps)

        if wait:
            self.await_stop(timeout=timeout)

            if reset_speed and velocity_changed:
                self.set_slew_speed(initial_scan_speed)

        return actual_scan_speed

    def home(self):
        """ This is implemented by the derived class below. """
        raise NotImplementedError("This model does not support limit switches and, therefore, has no homing feature.")


class McPherson789A4WithLimitSwitches(McPherson789A4):
    _HAS_LIMIT_SWITCHES = True
    DEFAULT_HOMING_TIMEOUT = 60 * 5  # Depending on the initial motor position and velocity, this may take a while.
    DEFAULT_HOMING_SPEED = 23000  # As documented in the manual.
    FAST_HOMING_SPEED = 3000000  # As documented in the manual.
    EDGE_DETECTION_SPEED = 1000  # As documented in the manual.

    def initialize(self, visa_id, steps_per_rev=36000, timeout=1, home_on_startup=True):
        super().initialize(visa_id, steps_per_rev=steps_per_rev, timeout=timeout)

        self.home_on_startup = home_on_startup
        if not self.home_on_startup:
            warnings.warn("It is strongly recommended to home on startup before proceeding with anything else!")

    def _open(self, *args, **kwargs):
        self.instrument = super()._open(*args, **kwargs)

        if self.home_on_startup:
            self.home()

        return self.instrument

    def get_limit_status(self):
        """ Query the device for limit status.

        :return: LimitSwitchStatus.LOW, LimitSwitchStatus.HIGH, LimitSwitchStatus.INBETWEEN. NOTE: This does not return
                 LimitSwitchStatus.HOME for that equivalent functionality call self.is_home().
        """
        resp = np.int32(self.command(ASCIIControlCodes.GET_LIMIT_SWITCH_STATUS))

        is_home = resp & np.int32(LimitSwitchStatus.HOME.value)

        if is_home:
            resp = resp - np.int32(LimitSwitchStatus.HOME.value)

        status = LimitSwitchStatus(resp)

        return status

    def poll_limit_status(self, break_conditions, *args, **kwargs):
        """ Poll device for limit status. See catkit.util.poll_status() for more info. """
        return catkit.util.poll_status(break_conditions, self.get_limit_status, *args, **kwargs)

    def is_home(self, toggle_home_switch=True):
        """ Query whether the device is in the HOME position/region.

        :param toggle_home_switch: bool (optional) - If the home switch is disabled it is not possible to query it. This
                                                     func will enable it if toggle_home_switch is True. It will also
                                                     disable it once queried. This functionality may not be desired when
                                                     e.g., homing, where the home switch must not be disabled.

        :return: bool. NOTE: If the home switch is disabled and toggle_home_switch=False this will always return False.
        """

        if toggle_home_switch:
            self.command(ASCIIControlCodes.ENABLE_HOME_SWITCH)

        try:
            resp = np.int32(self.command(ASCIIControlCodes.GET_LIMIT_SWITCH_STATUS))
            return bool(resp & np.int32(LimitSwitchStatus.HOME.value))
        finally:
            if toggle_home_switch:
                self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)

    def await_home(self, timeout=DEFAULT_POLL_TIMEOUT):
        """ Wait for device to indicate it is in the home position/region. Poll the device at intervals of
        self.QUERY_DELAY until it is in the home position/region.

        NOTE: The home switch must be explicitly enabled before calling this.

        :param timeout: int, float (optional) - Raise TimeoutError if the devices isn't at home within timeout seconds.
                                                0, None, & negative values => infinite timeout.
        """

        poll_func = functools.partial(self.is_home, toggle_home_switch=False)
        catkit.util.poll_status((True,), poll_func, timeout=timeout)

    def await_not_home(self, timeout=DEFAULT_POLL_TIMEOUT):
        """ Wait for device to indicate it is NO LONGER in the home position/region. Poll the device at intervals of
        self.QUERY_DELAY until it is NO LONGER in the home position/region.

        NOTE: The home switch must be explicitly enabled before calling this.

        :param timeout: int, float (optional) - Raise TimeoutError if the devices is still at home within timeout seconds.
                                                0, None, & negative values => infinite timeout.
        """

        poll_func = functools.partial(self.is_home, toggle_home_switch=False)
        catkit.util.poll_status((False,), poll_func, timeout=timeout)

    def find_edge(self, steps_per_second, timeout=DEFAULT_POLL_TIMEOUT):
        """ Find the upper edge of the home region. This is the actual "home" position.

        NOTE: This only moves in the up direction and, therefore, the motor must be below the edge, in the home region.
              Raises a RuntimeError ff not in the home region when called.

        :param steps_per_second: int - Velocity at which to move. This should be slow.
        :param timeout: int (optional) - The timeout passed to self.await_stop().
        """
        # NOTE: When edge is found the position is just + of the home region such that self.is_home := False.

        if not self.is_home(toggle_home_switch=False):
            raise RuntimeError("Home switch must be enabled and motor within the home region to find edge.")

        # Enable "high accuracy" circuit.
        try:
            self.command(ASCIIControlCodes.ENABLE_HIGH_ACCURACY_HOMING)
            self.command(ASCIIControlCodes.FIND_EDGE, steps_per_second)
            self.await_stop(timeout=timeout)
        finally:
            self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)

    def home(self, steps_per_second=DEFAULT_HOMING_SPEED, edge_detection_velocity=EDGE_DETECTION_SPEED,
             timeout=DEFAULT_HOMING_TIMEOUT, fast=False):
        """ Complete homing procedure to find the home position which is defined as the upper edge of the home region.


        NOTE: This procedure is as outlined in the manual.
        NOTE: When edge is found the position is just + of the home region such that self.is_home := False.
        NOTE: The Home region is wide and includes the low limit.
        NOTE: For steps_per_second = 3e6 it takes ~210s to move from the low limit to the high limit and ~117s from
              the high to home.
              For steps_per_second = 23000 it takes ~470s to move from the low limit to the high limit and ~260s
              from the high to home.
                  Suitable timeouts must therefore be used.

        :param steps_per_second: int (optional) - The velocity used when finding the home region.
        :param edge_detection_velocity: int (optional) - The velocity passed to self.find_edge().
        :param timeout: int, float (optional) - The timeout used to wait upon individual moves within this procedure.
                                                NOTE: It is NOT the timeout for the overall complete homing procedure.
        :param fast: bool (optional) - If True, overrides steps_per_second=self.FAST_HOMING_SPEED.
                                       TODO: The backlash section of this procedure needs calibrating and may fail.
        """
        if fast:
            steps_per_second = self.FAST_HOMING_SPEED

        if steps_per_second > self.DEFAULT_HOMING_SPEED:
            warnings.warn(f"Uncalibrated backlash for speed: {steps_per_second} (>{self.DEFAULT_HOMING_SPEED}). Homing may fail.")

        print("Homing in progress... (this may take a while)")  # TODO: Should be self.log().
        t0 = time.perf_counter()
        try:
            # Enable home circuit.
            self.command(ASCIIControlCodes.ENABLE_HOME_SWITCH)

            # Check whether already in home region and move accordingly.
            if self.is_home(toggle_home_switch=False):
                self.start_motion(steps_per_second=steps_per_second)
                self.await_not_home(timeout=timeout)
            else:
                self.start_motion(steps_per_second=-steps_per_second)
                self.await_home(timeout=timeout)

            # Stop.
            self.stop_motion()

            # The high accuracy edge detection circuit only moves in the + direction and, therefore, we need to be far
            # enough below the edge of the home position to give it room to work.

            # TODO: It is the following two steps that aren't calibrated for velocities other than that outlined in the
            #  manual. It may even fail when using the faster velocity stated in the manual - it did numerous times
            #  whilst testing.

            # Move further down into home region (3 motor revs).
            self.slew(-self.steps_per_rev*3, wait=True)

            # Remove some backlash from the last move (2 motor revs).
            self.slew(self.steps_per_rev*2, wait=True)

            # Find edge of homing switch.
            # NOTE: Depending on the speed used to find the home region, the last two steps may have actually moved the
            # motor beyond the home region which will cause self.find_edge() to raise.
            self.find_edge(steps_per_second=edge_detection_velocity, timeout=timeout)

            print(f"Homing complete. ({time.perf_counter() - t0}s)")  # TODO: Should be self.log().
        finally:
            self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)
