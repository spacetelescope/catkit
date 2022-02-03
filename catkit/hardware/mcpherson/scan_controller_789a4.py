import enum
import time
import warnings

from catkit.interfaces.Instrument import Instrument
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
    INIT = ' '
    END_OF_CMD = '\r'
    SOFT_STOP = '@'  # Causes deacceleration to stop.
    RESET = "\x03".encode("ascii")  # Stops motion, sets counter to 0, assumes idle state.
    DISABLE_HOME_SWITCH = "A0"
    ENABLE_HOME_SWITCH = "A8"
    ENABLE_HIGH_ACCURACY_HOMING = "A24"
    # CLEAR = "C1"
    FIND_EDGE = 'F'
    # EXEC_INTERNAL_FUNC = 'G'
    START_VELOCITY = 'I'
    RAMP_SLOPE = 'K'
    # PROGRAM_MODE = 'P'
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
    UNKNOWN = 0  # Not at any of the below.
    HOME = 32
    HIGH = 64
    LOW = 128


class MotionStatus(enum.Enum):
    STOPPED = 0
    MOVING = 1
    HIGH = 2
    SLEWING = 16


class McPherson789A4(Instrument):  # TODO: Write interface.

    instrument_lib = pyvisa

    _HAS_LIMIT_SWITCHES = False  # Use McPherson789A4WithLimitSwitches if True.

    BAUD_RATE = 9600
    DATA_BITS = 8
    STOP_BITS = 1
    PARITY = None
    FLOW_CONTROL = None
    ENCODING = "ascii"
    QUERY_TIMEOUT = 800  # ms
    HEADER_TIMEOUT = 20000  # ms

    def initialize(self, visa_id, steps_per_rev=36000, timeout=1):
        self.visa_id = visa_id
        self.timeout = timeout
        self.instrument_lib = self.instrument_lib.ResourceManager("@py")
        self.timeout = max(self.QUERY_TIMEOUT, self.HEADER_TIMEOUT)  # TODO: ?
        self._name = self.__class__.__name__

        self.steps_per_rev = steps_per_rev

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
                                           # TODO: Check the following for correctness.
                                           write_termination='\r',
                                           read_termination='\r')

        self.command(ASCIIControlCodes.INIT)
        self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)
        return self.instrument

    def _close(self):
        if self.instrument:
            try:
                self.stop()
                self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)
            finally:
                self.instrument.close()

    def command(self, cmd):
        if cmd not in ASCIIControlCodes:
            raise TypeError(f"Only {ASCIIControlCodes.__name__} commands allowed.")
        elif cmd is ASCIIControlCodes.GET_MOTION_STATUS:
            return self.instrument.query_ascii_values(cmd.value)
        elif cmd is ASCIIControlCodes.GET_LIMIT_SWITCH_STATUS:
            if not self._HAS_LIMIT_SWITCHES:
                raise NotImplementedError("This model does not support limit switches.")
            return self.instrument.query_ascii_values(cmd.value)
        else:
            if not self._HAS_LIMIT_SWITCHES and cmd in (ASCIIControlCodes.ENABLE_HIGH_ACCURACY_HOMING,
                                                        ASCIIControlCodes.ENABLE_HOME_SWITCH,
                                                        ASCIIControlCodes.FIND_EDGE):
                raise NotImplementedError("This model does not support limit switches.")
            self.instrument.write_ascii_values(cmd.value)

    def get_motion_status(self):
        return MotionStatus(int(self.command(ASCIIControlCodes.GET_MOTION_STATUS)))

    def is_moving(self):
        return self.get_motion_status() is not MotionStatus.STOPPED

    def poll_status(self, break_conditions, func, timeout=DEFAULT_POLL_TIMEOUT, poll=DEFAULT_POLL):
        """ Used to poll status whilst motor is in motion.
            NOTE: If the poll duration is too long for the given motor speed it is possible to miss the desired status.
        """
        status = None
        counter = 0
        while counter < timeout:
            status = func()
            if status in break_conditions:
                break

            time.sleep(poll)
            counter += poll

        if counter >= timeout:
            raise RuntimeError(f"Motor failed to complete operation within {timeout}s")

        return status

    def poll_motion(self, break_conditions, timeout=DEFAULT_POLL_TIMEOUT, poll=DEFAULT_POLL):
        return self.poll_status(break_conditions, self.get_motion_status, timeout=timeout, poll=poll)

    def await_stop(self, timeout=DEFAULT_POLL_TIMEOUT, poll=DEFAULT_POLL):
        self.poll_motion((MotionStatus.STOPPED,), timeout=timeout, poll=poll)

    def soft_stop(self, timeout=DEFAULT_POLL_TIMEOUT, poll=DEFAULT_POLL):
        """ Send command to stop motor then wait on confirmation that it has actually stopped. """
        self.command(ASCIIControlCodes.SOFT_STOP)
        self.await_stop(timeout=timeout, poll=poll)

    def stop(self, timeout=DEFAULT_POLL_TIMEOUT, poll=DEFAULT_POLL):
        """ Send command to stop motor then wait on confirmation that it has actually stopped. """
        self.command(ASCIIControlCodes.RESET)
        self.await_stop(timeout=timeout, poll=poll)

    def scan(self, steps_per_second):
        """ Constantly velocity motion until either hitting a limit or motion explicitly stopped.
            NOTE: The manual seems to imply that "limit" may not include the "home" limit.
        """
        msg = f"{ASCIIControlCodes.CONSTANT_VELOCITY_MOVE.value}{steps_per_second}"
        self.instrument.write_ascii_values(msg)

    def relative_move(self, steps, steps_per_second=None):
        """ Move motor by a number of steps at a given speed. """
        cmd = ASCIIControlCodes.SCAN_UP if steps >= 0 else ASCIIControlCodes.SCAN_DOWN

        if steps_per_second is not None:
            # Set speed.
            # TODO: Query initial speed so we can reset speed post move?
            msg = f"{ASCIIControlCodes.SCAN_SPEED}{steps_per_second}"
            self.instrument.write_ascii_values(msg)

        msg = f"{cmd.value}{steps}"
        self.instrument.write_ascii_values(msg)

    def home(self):
        raise NotImplementedError("This model does not support limit switches and therefore has no homing feature.")


class McPherson789A4WithLimitSwitches(McPherson789A4):
    _HAS_LIMIT_SWITCHES = True

    def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)

        self._home_on_startup = True
        if not self._home_on_startup:
            warnings.warn("It is strongly recommended to home on startup before proceeding with anything else! ")

    def _open(self, *args, **kwargs):
        self.instrument = super()._open(*args, **kwargs)

        if self._home_on_startup:
            self.home()

        return self.instrument

    def get_limit_status(self):
        return LimitSwitchStatus(int(self.command(ASCIIControlCodes.GET_LIMIT_SWITCH_STATUS)))

    def poll_limit_status(self, break_conditions, timeout=DEFAULT_POLL_TIMEOUT, poll=DEFAULT_POLL):
        return self.poll_status(break_conditions, self.get_limit_status, timeout=timeout, poll=poll)

    def is_home(self):
        return self.get_limit_status() is LimitSwitchStatus.HOME.value

    def find_edge(self, steps_per_second):
        if not self.is_home():
            raise RuntimeError("Not in home position.")

        # Enable "high accuracy" circuit.
        self.command(ASCIIControlCodes.ENABLE_HIGH_ACCURACY_HOMING)

        msg = f"{ASCIIControlCodes.FIND_EDGE}{steps_per_second}"
        self.instrument.write_ascii_values(msg)

    def home(self, timeout=DEFAULT_POLL_TIMEOUT, poll=DEFAULT_POLL):
        """ This requires the use of limit switches. There are two procedures depending on the initial position.
            NOTE: This procedure is as outlined in the manual.
        """

        # TODO: The procedure in the manual seems dubious - specifically the asymmetry based upon initial position???

        self.log("Homing in progress...")
        t0 = time.perf_counter()
        try:
            # Enable home circuit.
            self.command(ASCIIControlCodes.ENABLE_HOME_SWITCH)

            initial_direction = 1  # +/- 1.

            # Check whether already in home position, if so, move off so that accurate homing can occur.
            # TODO: Why move off only to move back?
            if self.is_home():
                self.scan(steps_per_second=initial_direction * 23000)

                # Poll limit switch status until not in home position (break loop when status is anything but HOME).
                self.poll_limit_status([x for x in LimitSwitchStatus if x is not LimitSwitchStatus.HOME],
                                       timeout=timeout,
                                       poll=poll)

                # Soft stop.
                self.command(ASCIIControlCodes.SOFT_STOP)
                direction = -1 * initial_direction
            else:
                # Not in home position but in which direction is home?
                # Find home.
                # NOTE: Manual suggests '-' (negative) direction so we'll start with that.
                initial_direction = -1
                self.scan(steps_per_second=initial_direction * 23000)

                # Poll limit switch status until a switch is hit (break loop when status is not UNKOWN).
                status = self.poll_limit_status((LimitSwitchStatus.UNKNOWN,), timeout=timeout, poll=poll)

                if status is LimitSwitchStatus.HOME:
                    # We found home.
                    direction = -1 * initial_direction
                elif status is LimitSwitchStatus.HIGH:
                    # Whoops we went the wrong way and hit a limit.
                    direction = -1 * initial_direction

                    # Move back the other way until we hit home.
                    self.scan(steps_per_second=direction * 23000)
                    self.poll_limit_status((LimitSwitchStatus.HOME,), timeout=timeout, poll=poll)

                elif status is LimitSwitchStatus.LOW:
                    # Whoops we went the wrong way and hit a limit.
                    direction = -1 * initial_direction

                    # Move back the other way until we hit home.
                    self.scan(steps_per_second=direction * 23000)
                    self.poll_limit_status((LimitSwitchStatus.HOME,), timeout=timeout, poll=poll)

            # Back into home position by 3 motor revolutions.
            self.relative_move(steps=direction * 3 * self.steps_per_rev)

            # Remove backlash (by 2 motor revolutions).
            reverse_direction = direction * -1
            self.relative_move(steps=reverse_direction * 2 * self.steps_per_rev)

            # Find edge of homing flag.
            self.find_edge(direction*1000)

            self.log(f"Homing complete. ({time.perf_counter() - t0})s")
        finally:
            self.command(ASCIIControlCodes.DISABLE_HOME_SWITCH)
