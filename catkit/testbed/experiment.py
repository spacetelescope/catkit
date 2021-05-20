from abc import ABC, abstractmethod
import logging
import os
import _thread
import threading
import uuid

from catkit import datalogging
from catkit.multiprocessing import DEFAULT_TIMEOUT, EXCEPTION_SERVER_ADDRESS, Process, SharedMemoryManager


STOP_EVENT = "hicat_stop_event"
SAFETY_EVENT = "hicat_safety_event"
SAFETY_BARRIER = "hicat_safety_barrier"


class SafetyException(Exception):
    pass


class StopException(Exception):
    pass


class SafetyTest(ABC):
    def __init__(self, *args, max_consecutive_failures=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = None
        self.log = logging.getLogger()

        # Permit <max_consecutive_failures> consecutive failures before failing test and raising.
        self.max_consecutive_failures = max_consecutive_failures
        self.consecutive_failure_counter = 0

    def do_check(self, force_raise=False):
        try:
            self.check()
        except Exception as error:
            if force_raise:
                raise

            self.consecutive_failure_counter += 1
            if self.consecutive_failure_counter > self.max_consecutive_failures:
                raise
            else:
                self.log.warning(f"Safety test warning issued for {self.name}: {error}")
        else:
            self.consecutive_failure_counter = 0

    @abstractmethod
    def check(self):
        """Implement to conduct safety check and raise a SafetyException upon failure. """


class Testbed:
    """ Class for owning testbed infrastructure such as any shared memory servers and running safety checks. """

    def __init__(self, safety_tests, output_path=None, suffix=None,
                 safety_check_interval=60):
        """
        Parameters
        ----------
        safety_tests : list
            List of SafetyTest class defs, not already instantiated objects (nothing else should own these).
        safety_check_interval : int, float, optional:
            Time interval between calling check_safety().
        output_path: str, optional
            Output directory to write all files to (or to subdirectories thereof).
             For the vast majority of use cases this should be left as None, in which
             case it will be auto-generated based on date-time + suffix.
        suffix : str, optional
            Descriptive string to include as part of the path.
        """
        self.log = None
        self.output_path = output_path
        self.suffix = suffix
        self.init_path()
        self.init_log()

        self.safety_check_interval = safety_check_interval

        self.exception_manager = SharedMemoryManager(address=EXCEPTION_SERVER_ADDRESS, own=True)
        self.stop_event = None
        self.safety_event = None
        self.barrier = None

        self.safety_process = None
        self.safety_tests = []

        for test in safety_tests:
            self.safety_tests.append(test())

    def __enter__(self):
        try:
            self._setup()

            assert self.stop_event is not None
            assert self.safety_event is not None

            # Run an initial test before starting continuous monitoring.
            # NOTE: These initial tests will always raise upon failure, irrespective of a test's max_consecutive_failures.
            self.check_safety(force_raise=True)

            # Start continuous monitoring.
            self.safety_process = Process(target=self.safety_monitor, name="Safety Test Monitor", args=(self.barrier,))
            self.safety_process.start()  # NOTE: This will need to be joined.
            # print(f" ### Safety tests monitored on PID: {self.safety_process.pid}")
            self.log.info(f"Continuously monitoring safety tests... (on PID: {self.safety_process.pid})")

            # Don't return until continuous monitoring has started.
            self.barrier.wait()

            return self
        except Exception:
            try:
                try:
                    self.log.exception("The testbed encountered the following error(s):")
                finally:
                    # NOTE: __exit__() is not called if this func raises.
                    self._teardown()
            finally:
                raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._teardown()
        finally:
            if exc_type:
                self.log.exception("The testbed encountered the following error(s):")

    def _setup(self):
        """ Setup the necessary exception manager server and run safety check monitor.
            Override this to start and context manage any and all other servers.
        """
        # Start server to catch and manage exceptions from parallel processes.
        self.exception_manager.start()  # NOTE: This is joined in self._teardown().
        self.stop_event = self.exception_manager.get_event(STOP_EVENT)
        self.safety_event = self.exception_manager.get_event(SAFETY_EVENT)
        self.barrier = self.exception_manager.get_barrier(SAFETY_BARRIER, parties=2)

    def check_safety(self, *args, **kwargs):
        self.log.info("Running safety tests...")
        for safety_test in self.safety_tests:
            try:
                safety_test.do_check(*args, **kwargs)
            except Exception:
                # NOTE: This order is critical such that self.safety_event is set before self.stop_event.wait() wakes.
                self.safety_event.set()
                self.stop_event.set()
                raise

        self.log.info("All Safety tests passed!")

    def safety_monitor(self, barrier):
        """ Monitor all safety checks.
            NOTE: This is run on a child process.
        """
        self.init_log()

        barrier.wait()

        while not self.stop_event.is_set():
            # NOTE: Upon failure, self.check_safety(), sets both self.safety_event and self.stop_event, and raises a
            # SafetyException (in that order).
            self.check_safety()
            self.stop_event.wait(self.safety_check_interval)

    def _teardown(self):
        """ Override this to stop/join/shutdown any and all other servers started by setup(). """
        try:
            try:
                try:
                    if self.log:
                        self.log.info(" Cleaning up (teardown)...")
                finally:
                    # Stop the safety monitor process so that it can be joined.
                    # NOTE: This will also stop EVERYTHING else - no safety := no experiment.
                    if self.stop_event:
                        self.stop_event.set()
            finally:
                if self.safety_process:
                    self.safety_process.join(DEFAULT_TIMEOUT)
        finally:
            # Shutdown the exception handler manager.
            # NOTE: self.stop_event and self.safety_event are local to the exception manager server process and
            # will not be accessible post shutdown.
            if self.exception_manager is not None:
                self.exception_manager.shutdown()

    def init_path(self):
        """ Set up output. """
        pass

    def init_log(self):
        """ Initialize log writing.
            Override to setup log handlers etc.
        """
        self.log = logging.getLogger()


class Experiment:
    """
    Base class that instills safety monitoring into any class that inherits it.  Subclasses
    need to implement a function called "experiment()".
    """
    name = "Base Experiment"

    log = logging.getLogger()
    data_log = datalogging.get_logger(__name__)

    def __init__(self, output_path=None, suffix=None, stop_all_on_exception=True, run_forever=False,
                 disable_shared_memory=False):
        """ Initialize attributes common to all Experiments.
        All child classes should implement their own __init__ and call this via super()

        Parameters
        ----------
        output_path: str, optional
            Output directory to write all files to (or to subdirectories thereof).
             For the vast majority of use cases this should be left as None, in which
             case it will be auto-generated based on date-time + suffix.
        suffix : str, optional
            Descriptive string to include as part of the path.
        run_forever : bool, optional
            Allows the experiment to continue running even when concurrent experiments have set the global stop event.
            It will, however, stop for a safety event.
        stop_all_on_exception : bool, optional
            Allows peripheral concurrent experiments to run and fail, for example, from syntax errors without stopping
            all other experiments.
        disable_shared_memory : bool, optional
            Disable shared memory. When True some peripheral shared memory will still exist and the main
            experiment will run on the parent process. When False, the main experiment is run on a child process.
        """
        self.output_path = output_path
        self.suffix = suffix
        self.stop_all_on_exception = stop_all_on_exception
        self.run_forever = run_forever
        self.disable_shared_memory = disable_shared_memory

        self.exception_manager = SharedMemoryManager(address=EXCEPTION_SERVER_ADDRESS, own=False)
        self.experiment_process = None
        self.stop_event = None
        self.safety_event = None
        self._event_monitor_barrier = None
        self._kill_event_monitor_event = None

        self.pre_experiment_return = None
        self.experiment_return = None
        self.post_experiment_return = None

        self.init_path()
        self.init_log()

    def join(self, *args, **kwargs):
        if self.experiment_process:
            self.experiment_process.join(*args, **kwargs)

    def start(self):
        """ Start the experiment on a separate process and then returns (is non-blocking, it does not wait).
            It works like multiprocessing.Process.start(), a join() is thus required.
        """
        # Check that we can connect from the parent process.
        self.exception_manager.connect()  # Needs to have already been started.
        self.stop_event = self.exception_manager.get_event(STOP_EVENT)
        self.safety_event = self.exception_manager.get_event(SAFETY_EVENT)

        try:
            if self.disable_shared_memory:
                self.log.info(f"Running experiment on parent process (PID: {os.getpid()})...")
                self.run_experiment()
            else:
                # Start the process to run the experiment.
                self.log.info("Creating separate process to run experiment...")
                self.experiment_process = Process(target=self.run_experiment, name=self.name)
                self.experiment_process.start()
                # print(f" ### Child experiment process on PID: {self.experiment_process.pid}")
                self.log.info(f"{self.name} process started on PID: {self.experiment_process.pid}")
        except Exception:
            if self.stop_all_on_exception:
                self.stop_event.set()
            raise

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.join()

    def event_monitor(self):
        """ This is run on a thread on the child process running self.experiment(). It monitors events and then raises
            to stop parent thread running self.experiment().
            NOTE: It doesn't explicitly stop the parent process, it will implicitly stop the parent process if it's
            waiting in a join() (which it needs to be).
        """

        try:  # This must always be running, so stop main thread upon exception.
            self._event_monitor_barrier.wait()  # Used to sync with the main thread so that it doesn't proceed without being monitored.

            # Wait indefinitely (this is run on a daemonic thread).
            if self.run_forever:
                # Ignore stop_event but DON'T ignore safety_event.
                self.safety_event.wait()
            else:
                # NOTE: self.stop_event is set upon a safety check failure as well as self.safety_event, so waiting on
                # self.stop_event is effectively waiting on self.safety_event also.
                self.stop_event.wait()
        finally:
            # NOTE: This event monitor can be killed WITHOUT raising SIGINT (as it does below) by setting
            # self._kill_event_monitor_event BEFORE setting self.stop_event.
            if self._kill_event_monitor_event.is_set():
                return
            # Interrupt the main thread with a KeyboardInterrupt exception.
            # NOTE: This won't interrupt time.sleep(). See https://docs.python.org/3/library/time.html#time.sleep
            _thread.interrupt_main()

    def run_experiment(self):
        """ Code executed on the child process. """
        self.init_log()
        data_log_writer = None

        if not self.disable_shared_memory:
            # Check that we can connect from the child process.
            self.exception_manager = SharedMemoryManager(address=EXCEPTION_SERVER_ADDRESS, own=False)
            self.exception_manager.connect()  # Needs to have already been started.
            self.stop_event = self.exception_manager.get_event(STOP_EVENT)
            self.safety_event = self.exception_manager.get_event(SAFETY_EVENT)

        self._event_monitor_barrier = threading.Barrier(parties=2, timeout=DEFAULT_TIMEOUT)
        self._kill_event_monitor_event = threading.Event()
        monitor_thread = threading.Thread(target=self.event_monitor, daemon=True)
        monitor_thread.start()

        try:
            try:  # Catches SIGINT issued, using _thread.interrupt_main(), by the event_monitor.
                self._event_monitor_barrier.wait()  # Wait for the monitor_thread to be ready.

                # Set up data log writer
                data_logger_path = os.path.join(self.output_path, self.name.replace(" ", "_").lower() + "_data_logger")
                data_log_writer = datalogging.DataLogWriter(data_logger_path)
                datalogging.DataLogger.add_writer(data_log_writer)

                # Run pre-experiment code, e.g., open devices, run calibrations, etc.
                self.log.info("Experiment.pre_experiment() running...")
                self.pre_experiment_return = self.pre_experiment()
                self.log.info("Experiment.pre_experiment() completed.")

                # Run the core experiment.
                self.log.info("Experiment.experiment() running...")
                self.experiment_return = self.experiment()
                self.log.info("Experiment.experiment() completed.")

                # Run any post-experiment analysis, etc.
                self.log.info("Experiment.post_experiment() running...")
                self.post_experiment_return = self.post_experiment()
                self.log.info("Experiment.post_experiment() completed.")
            except KeyboardInterrupt:
                if self.safety_event.is_set():
                    raise SafetyException("Event monitor detected a SAFETY event before experiment completed (join root experiment and/or call teardown to retrieve safety exception).")
                elif self.safety_event.is_set():
                    raise StopException("Event monitor detected a STOP event before experiment completed (join root experiment and/or call teardown to retrieve safety exception).")
                else:
                    # An actual ctrl-c like interrupt occurred.
                    raise
        except (Exception, KeyboardInterrupt):  # KeyboardInterrupt inherits from BaseException not Exception.
            self.log.exception("Exception caught during Experiment.run_experiment().")
            if self.stop_all_on_exception:
                # NOTE: An exception has been raised by the experiment and NOT by the event monitor. We now won't to
                # kill the event monitor without it calling _thread.interrupt_main(). We do this by setting
                # self. _kill_event_monitor_event BEFORE setting self.stop_event. Otherwise, setting stop_event would
                # cause the event monitor to call _thread.interrupt_main() thus killing the main child thread, possibly
                # before Process.run has a chance to set the exception on the exception manager server.
                self._kill_event_monitor_event.set()
                self.stop_event.set()
            raise
        finally:
            # Stop the event monitor.
            self._kill_event_monitor_event.set()

            # Release data log writer
            if data_log_writer:
                datalogging.DataLogger.remove_writer(data_log_writer)
                data_log_writer.close()

    def pre_experiment(self, *args, **kwargs):
        """ This is called immediately BEFORE self.experiment(). """
        pass

    def experiment(self, *args, **kwargs):
        """ This is where the experiment gets implemented. All concrete child classes must implement this. """

    def post_experiment(self, *args, **kwargs):
        """ This is called immediately AFTER self.experiment(). """
        pass

    def init_path(self):
        """ Set up experiment output. """
        pass

    def init_log(self):
        """ Initialize log writing. """
        pass
