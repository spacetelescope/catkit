from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from abc import *
from multiprocessing import Process
from ..hardware.testbed import *
from ..hardware.thorlabs.ThorlabsTSP01 import *
from .. config import CONFIG_INI
import time

"""Abstract base class that instills safety monitoring into any class that inherits it."""


class Experiment(object):
    __metaclass__ = ABCMeta

    # Constructor.
    def __init__(self, *args, **kwargs):
        """Stores monitoring variables into self and calls subclass's initialize function."""
        self.interval = CONFIG_INI.getint("safety", "check_interval")
        self.min_humidity = CONFIG_INI.getint("safety", "min_humidity")
        self.max_humidity = CONFIG_INI.getint("safety", "max_humidity")
        self.min_temp = CONFIG_INI.getint("safety", "min_temp")
        self. max_temp = CONFIG_INI.getint("safety", "max_temp")
        self.__initialize(*args, **kwargs)

    @abstractmethod
    def __initialize(self, *args, **kwargs):
        """Should be used to store all experiment variables into self, and perform any other set up that needs
        to happen before starting. All child classes must implement this."""

    @abstractmethod
    def experiment(self):
        """This is where the experiment gets implemented. All child classes must implement this."""

    def start(self):
        """
        This function starts the experiment on a separate process and monitors power and humidity while active.
        Do not override.
        """
        experiment_process = Process(target=self.__run_experiment)
        experiment_process.start()
        ups = backup_power()
        safety_warning = False

        while experiment_process.is_alive():

            # Check that the UPS not on battery power.
            power_ok = ups.is_shutdown_needed()

            # Check humidity sensor.
            temp_ok, humidity_ok = self.__check_temp_humidity()

            # A shut down will occur after the safety check fails twice in a row.
            if power_ok and temp_ok and humidity_ok:

                # Clear the safety_warning flag, everything is ok.
                safety_warning = False

                # Sleep until it is time to check safety again.
                time.sleep(self.interval)

            elif safety_warning:

                # Shut down the experiment (but allow context managers to exit properly).
                util.soft_kill(experiment_process.pid)

            else:
                safety_warning = True
                print("Safety failure detected, experiment will be softly killed if safety check fails again.")

    def __run_experiment(self):
        """Wrapper for experiment to catch the softkill function's KeyboardInterrupt signal more gracefully."""
        try:
            self.experiment()
        except KeyboardInterrupt:
            # Silently catch KeyboardInterrupt exception used to kill experiment.
            pass

    def __check_temp_humidity(self):
        """
        Helper function that returns booleans for whether the temperature and humidity are ok.
        :return: Two booleans: temp_ok, humidity_ok.
        """
        temp, humidity = get_temp_humidity()
        temp_ok = self.min_temp <= temp <= self.max_temp
        humidity_ok = self.min_humidity <= humidity <= self.max_humidity
        return temp_ok, humidity_ok
