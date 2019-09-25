from abc import ABC, abstractmethod
from multiprocessing import Process

import time
import logging

from hicat.config import CONFIG_INI
from hicat import util
from hicat.experiments.SafetyTest import UpsSafetyTest, HumidityTemperatureTest, WeatherWarningTest, SafetyException


class Experiment(ABC):
    """
    Abstract base class that instills safety monitoring into any class that inherits it.  Subclasses
    need to implement a function called "experiment()", which is designated as an abstractmethod here.
    """
    name = None

    log = logging.getLogger(__name__)
    interval = CONFIG_INI.getint("safety", "check_interval")
    safety_tests = [UpsSafetyTest(), HumidityTemperatureTest()]#, WeatherWarningTest()]

    def __init__(self, output_path=None, suffix=None):
        """ Initialize attributes common to all Experiments.
        All child classes should implement their own __init__ and call this via super()

        :param output_path: Output directory to write all files to (or to subdirectories thereof).
                     For the vast majority of use cases this should be left as None, in which
                     case it will be auto-generated based on date-time + suffix.
        :paran suffix: Descriptive string to include as part of the path.
        """
        # Default is to wait to set the path until the experiment starts (rather than the constructor)
        # but users can optionally pass in a specifc path if they want to do something different in a
        # particular case.
        self.output_path = output_path
        self.suffix = suffix

    @abstractmethod
    def experiment(self):
        """
        This is where the experiment gets implemented. All child classes must implement this.
        """

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
                print(msg)
                self.log.info(msg)
                if not status:
                    errmessage = safety_test.name + " reports unsafe conditions. Aborting experiment before start... Details: {}".format(msg)
                    print(errmessage)
                    self.log.critical(errmessage)
                    raise SafetyException(errmessage)
            self.log.info("Safety tests passed!")
            self.log.info("Creating separate process to run experiment...")
            # Spin off and start the process to run the experiment.
            experiment_process = Process(target=self.run_experiment)
            experiment_process.start()
            self.log.info(self.name + " process started")

            while experiment_process.is_alive():

                for safety_test in self.safety_tests:
                    status, message = safety_test.check()
                    if status:
                        # Check passed, clear any warning that might be set and proceed to sleep until next iteration.
                        self.log.info(message)
                        safety_test.warning = False

                    elif safety_test.warning:
                            # Shut down the experiment (but allow context managers to exit properly).
                            errmessage = safety_test.name + " reports unsafe conditions repeatedly. Aborting experiment! Details: {}".format(msg)
                            self.log.critical(errmessage)
                            util.soft_kill(experiment_process)
                            raise SafetyException(errmessage)

                    else:
                        errmessage = (message + "\n" +  "Warning issued for " + safety_test.name +
                              ". Experiment will be softly killed if safety check fails again.")
                        self.log.warning(errmessage)
                        safety_test.warning = True

                # Sleep until it is time to check safety again.
                if not self.__smart_sleep(self.interval, experiment_process):
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
            if experiment_process is not None:
                util.soft_kill(experiment_process)
            # must return SafetyException type specifically to signal queue to stop in typical calling scripts
            raise safety_exception

    def run_experiment(self):
        """
        Wrapper for experiment to catch the softkill function's KeyboardInterrupt signal more gracefully.
        Do not override.
        """
        try:
            self.init_experiment_path_and_log()
            self.experiment()
        except KeyboardInterrupt:
            self.log.warn("Child process: caught ctrl-c, raising exception.")
            raise

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

    def init_experiment_path_and_log(self):
        """Set up experiment output path and initialize log writing to there.
        Called from start() prior to experiment()

        Do not override.
        """

        if self.suffix is None:
            self.suffix = str(self.name).replace(" ","_").lower()

        if self.output_path is None:
            self.output_path = util.create_data_path(suffix=self.suffix)

        util.setup_hicat_logging(self.output_path, self.suffix)
