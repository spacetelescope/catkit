from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from abc import *
from multiprocessing import Process
from .. config import CONFIG_INI
from .. import util
from .SafetyTest import UpsSafetyTest, HumidityTemperatureTest, SafetyException
import time

"""Abstract base class that instills safety monitoring into any class that inherits it."""


class Experiment(object):
    __metaclass__ = ABCMeta

    interval = CONFIG_INI.getint("safety", "check_interval")
    safety_tests = [UpsSafetyTest(), HumidityTemperatureTest()]

    @abstractmethod
    def experiment(self):
        """This is where the experiment gets implemented. All child classes must implement this."""

    def start(self):
        """
        This function starts the experiment on a separate process and monitors power and humidity while active.
        Do not override.
        """
        print("Running safety tests...")
        # Check tests before starting experiment.
        for safety_test in self.safety_tests:
            if not safety_test.check():
                print(safety_test.name + " reports unsafe conditions. Aborting experiment...")
                raise SafetyException()
        print("Safety tests passed!")
        print("Creating separate process to run experiment...")
        # Spin off and start the process to run the experiment.
        experiment_process = Process(target=self.run_experiment)
        experiment_process.start()
        print("Experiment process started")

        while experiment_process.is_alive():

            for safety_test in self.safety_tests:

                if safety_test.check():
                    # Check passed, clear any warning that might be set and proceed to sleep until next iteration.
                    safety_test.warning = False

                elif safety_test.warning:
                        # Shut down the experiment (but allow context managers to exit properly).
                        util.soft_kill(experiment_process)
                        raise SafetyException()

                else:
                    print("Warning issued for " + safety_test.name +
                          ". Experiment will be softly killed if safety check fails again.")
                    safety_test.warning=True

            # Sleep until it is time to check safety again.
            if not self.__smart_sleep(self.interval, experiment_process):
                # Experiment ended before the next check interval, exit the while loop.
                break

    def run_experiment(self):
        """Wrapper for experiment to catch the softkill function's KeyboardInterrupt signal more gracefully."""
        try:
            self.experiment()
        except KeyboardInterrupt:
            # Silently catch KeyboardInterrupt exception used to kill experiment.
            pass

    @staticmethod
    def __smart_sleep(interval, process):
        """
        Sleep function that will return false at most 1 second after a process ends.  It sleeps in 1 second increments
        and checks if the process is alive each time.  Rather than sleeping for the entire interval.  This allows
        the master script to end when the experiment is finished.
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
