from abc import ABC, abstractmethod
import logging
import time

import catkit.util
from catkit.testbed import devices
from catkit import datalogging
from catkit.multiprocessing import Process


class SafetyTest(ABC):
    name = None
    warning = False

    @abstractmethod
    def check(self):
        """Implement to return two values: boolean for pass/fail, and a string for status message."""


class SafetyException(Exception):
    def __init__(self, *args):
        Exception.__init__(self, *args)


class Experiment(ABC):
    """
    Abstract base class that instills safety monitoring into any class that inherits it.  Subclasses
    need to implement a function called "experiment()", which is designated as an abstractmethod here.
    """
    name = None

    log = logging.getLogger(__name__)
    data_log = datalogging.get_logger(__name__)

    def __del__(self):
        self.clear_cache()

    def __init__(self, safety_tests, safety_check_interval=60, output_path=None, suffix=None):
        """ Initialize attributes common to all Experiments.
        All child classes should implement their own __init__ and call this via super()

        Parameters
        ----------
        safety_tests : list
            List of SafetyTest class defs, not already instantiated objects (nothing else should own these).
        safety_check_interval : int, float, optional:
            Time interval between calling each SafetyTest.chceck().
        output_path: str, optional
            Output directory to write all files to (or to subdirectories thereof).
             For the vast majority of use cases this should be left as None, in which
             case it will be auto-generated based on date-time + suffix.
        suffix : str, optional
            Descriptive string to include as part of the path.
        """
        # Default is to wait to set the path until the experiment starts (rather than the constructor)
        # but users can optionally pass in a specific path if they want to do something different in a
        # particular case.
        self.output_path = output_path
        self.suffix = suffix

        self.pre_experiment_return = None
        self.experiment_return = None
        self.post_experiment_return = None

        self.safety_check_interval = safety_check_interval
        self.safety_tests = []
        for test in safety_tests:
            self.safety_tests.append(test())

    def pre_experiment(self, *args, **kwargs):
        """ This is called immediately BEFORE self.experiment()."""
        pass

    @abstractmethod
    def experiment(self, *args, **kwargs):
        """ This is where the experiment gets implemented. All child classes must implement this. """

    def post_experiment(self, *args, **kwargs):
        """ This is called immediately AFTER self.experiment()."""
        pass

    def start(self):
        """
        This function starts the experiment on a separate process and monitors power and humidity while active.
        Do not override.
        """
        experiment_process = None
        try:

            self.log.info("Running safety tests...")
            # Check tests before starting experiment.
            for safety_test in self.safety_tests:
                status, msg = safety_test.check()
                # msg may have a newline in it; if so split that into separate log messages
                for msg_line in msg.split("\n"):
                    self.log.info(msg_line)
                if not status:
                    errmessage = safety_test.name + " reports unsafe conditions. Aborting experiment before start... Details: {}".format(msg)
                    print(errmessage)
                    self.log.critical(errmessage)
                    raise SafetyException(errmessage)
            self.log.info("Safety tests passed!")

            # Initialize experiment output path. Do this here so the output path is available in the parent process
            self.init_experiment_path()

            self.log.info("Creating separate process to run experiment...")
            # Spin off and start the process to run the experiment.
            experiment_process = Process(target=self.run_experiment, name=self.name)
            experiment_process.start()
            self.log.info(self.name + " process started")

            while experiment_process.is_alive():

                for safety_test in self.safety_tests:
                    status, message = safety_test.check()
                    if status:
                        # Check passed, clear any warning that might be set and proceed to sleep until next iteration.
                        for msg_line in message.split("\n"):
                            self.log.info(msg_line)
                        safety_test.warning = False

                    elif safety_test.warning:
                            # Shut down the experiment (but allow context managers to exit properly).
                            errmessage = safety_test.name + " reports unsafe conditions repeatedly. Aborting experiment! Details: {}".format(msg)
                            self.log.critical(errmessage)
                            catkit.util.soft_kill(experiment_process)
                            raise SafetyException(errmessage)

                    else:
                        errmessage = (message + "\n" +  "Warning issued for " + safety_test.name +
                              ". Experiment will be softly killed if safety check fails again.")
                        self.log.warning(errmessage)
                        safety_test.warning = True

                # Sleep until it is time to check safety again.
                if not self.__smart_sleep(self.safety_check_interval, experiment_process):
                    # Experiment ended before the next check interval, exit the while loop.
                    break
                    self.log.info("Experment ended before check interval; exiting.")
        except KeyboardInterrupt:
            self.log.exception("Parent process: caught ctrl-c, raising exception.")
            raise
        except SafetyException:
            self.log.exception("Safety exception.")
            raise
        except Exception as e:
            safety_exception = SafetyException("Monitoring process caught an unexpected problem: ", e)
            self.log.exception(safety_exception)
            # Shut down the experiment (but allow context managers to exit properly).
            if experiment_process is not None and experiment_process.is_alive():
                catkit.util.soft_kill(experiment_process)
            # must return SafetyException type specifically to signal queue to stop in typical calling scripts
            raise safety_exception

        # Explicitly join even though experiment_process.is_alive() will call join() if it's no longer alive.
        experiment_process.join()  # This will raise any child exceptions.

    def run_experiment(self):
        """
        Wrapper for experiment to catch the softkill function's KeyboardInterrupt signal more gracefully.
        Do not override.
        """

        data_log_writer = None

        # NOTE: This try/finally IS THE context manager for any cache cleared by self.clear_cache().
        try:
            self.init_experiment_log()

            # Set up data log writer
            data_log_writer = datalogging.DataLogWriter(self.output_path)
            datalogging.DataLogger.add_writer(data_log_writer)

            # De-restrict device cache access.
            global devices
            with devices:
                # Allow pre_experiment() to cache some devices to test for persistence (dev assertions only).
                self._persistence_checker = {}

                # Run pre-experiment code, e.g., open devices, run calibrations, etc.
                self.pre_experiment_return = self.pre_experiment()

                # Assert some devices remained opened.
                for device in self._persistence_checker.values():
                    assert device.instrument  # Explicit test that instrument remained open.

                # Run the core experiment.
                self.experiment_return = self.experiment()

                # Run any post-experiment analysis, etc.
                self.post_experiment_return = self.post_experiment()
        except KeyboardInterrupt:
            self.log.warning("Child process: caught ctrl-c, raising exception.")
            raise
        except Exception as error:
            self.log.exception(error)
            raise
        finally:
            self.clear_cache()

            # Release data log writer
            if data_log_writer:
                datalogging.DataLogger.remove_writer(data_log_writer)
                data_log_writer.close()

    @abstractmethod
    def clear_cache(self):
        """ Injection layer for deleting any global caches. """
        pass

    @staticmethod
    def __smart_sleep(interval, process):
        """
        Sleep function that will return false at most 1 second after a process ends.  It sleeps in 1 second increments
        and checks if the process is alive each time.  Rather than sleeping for the entire interval.  This allows
        the master script to end when the experiment is finished.
        Do not override.

        :param interval: check_interval from ini.
        :param process: experiment process to monitor while sleeping.
        :return: True if monitoring should continue, False if the experiment is done.
        """
        sleep_count = 0
        while process.is_alive():
            time.sleep(1)
            sleep_count += 1
            if sleep_count == interval:
                return True
        return False

    @abstractmethod
    def init_experiment_path(self):
        """ Set up experiment output. Called from start() prior to experiment(). """
        pass

    @abstractmethod
    def init_experiment_log(self):
        """ Initialize log writing. Called from run_experiment() prior to experiment(). """
        pass
