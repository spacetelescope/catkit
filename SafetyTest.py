from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import psutil
import logging
from datetime import datetime
import sys
if sys.version_info > (3,0):
    from urllib.request import urlopen
else:
    from urllib2 import urlopen
import xml.etree.cElementTree as ET
from abc import ABCMeta, abstractmethod
from ..hardware import testbed
from .. config import CONFIG_INI

# Note, SafetyTest is in the Experiments directory but is not itself an Experiment subclass.
# Rather it is part of the infrastructure used to enable running Experiments.

# safety related log messages should ALWAYS be displayed on screen, regardless of whether any other
# log handlers are present or not. Enforce this strictly by defining our own handler immediately on import.
safety_log = logging.getLogger('hicat_safety')
safety_log_handler = logging.StreamHandler()
safety_log_handler.setLevel(logging.WARNING)
safety_log.addHandler(safety_log_handler)


class SafetyTest(object):
    __metaclass__ = ABCMeta

    name = None
    warning = False

    @abstractmethod
    def check(self):
        """Implement to return two values: boolean for pass/fail, and a string for status message."""


class UpsSafetyTest(SafetyTest):

    name = "UPS Safety Test"

    # Create a SnmpUPS object to monitor the White UPS.
    ups = testbed.backup_power()

    def check(self):
        safety_log.debug("Checking UPS power up")
        return self.ups.is_power_ok(return_status_msg=True)


class HumidityTemperatureTest(SafetyTest):

    name = "Thorlabs Humidity and Temperature Sensor Safety Test"

    min_humidity = CONFIG_INI.getfloat("safety", "min_humidity")
    max_humidity = CONFIG_INI.getfloat("safety", "max_humidity")
    min_temp = CONFIG_INI.getfloat("safety", "min_temp")
    max_temp = CONFIG_INI.getfloat("safety", "max_temp")

    def check(self):
        if "TSP01GUI.exe" in (p.name() for p in psutil.process_iter()):
            status_msg = "Humidity and Temperature test failed: Close the Thorlabs GUI and run again. " \
                         "It interferes with our code."
            safety_log.error(status_msg)
            return False, status_msg

        temp, humidity = testbed.temp_sensor().get_temp_humidity()
        temp_ok = self.min_temp <= temp <= self.max_temp

        if temp_ok:
            status_msg = "Temperature test passed: {} falls between {} and {}.".format(
                temp, self.min_temp, self.max_temp)
            safety_log.debug(status_msg)
        else:
            status_msg = "Temperature test failed: {} is outside of {} and {}.".format(
                temp, self.min_temp, self.max_temp)
            safety_log.warning(status_msg)

        humidity_ok = self.min_humidity <= humidity <= self.max_humidity

        if humidity_ok:
            status_msg += "\nHumidity test passed: {} falls between {} and {}.".format(
                humidity, self.min_humidity, self.max_humidity)
            safety_log.debug(status_msg)
        else:
            status_msg += "\nHumidity test failed: {} is outside of {} and {}.".format(
                humidity, self.min_humidity, self.max_humidity)
            safety_log.warning(status_msg)

        return temp_ok and humidity_ok, status_msg


class WeatherWarningTest(SafetyTest):

    name = "National Weather Service MDC510 Warnings Safety Test"
    def check(self):
        wx_warning_list = CONFIG_INI.get("nws", "wx_warning_list")
        wx_url = CONFIG_INI.get("nws", "wx_url")
        warning_count = 0
        wx_data = urlopen(wx_url)
        tree = ET.parse(wx_data)
        wx_data.close()
        root = tree.getroot()
        currentDT = datetime.now()
        current_event = None
        for child in root:
            if 'entry' in str(child.tag):
                for wx_entry in child:
                    if 'event' in wx_entry.tag:
                        current_event = wx_entry.text
                    if 'effective' in wx_entry.tag:
                        start_time = wx_entry.text
                    if 'expires' in wx_entry.tag:
                        end_time = wx_entry.text

                if current_event:
                    safety_log.error("Event " + current_event + " from " + start_time + " to " + end_time)
                    if current_event in wx_warning_list:
                        # assume we're in our own timezone.
                        startDT = datetime.strptime(start_time[:-6], "%Y-%m-%dT%H:%M:%S")
                        endDT = datetime.strptime(end_time[:-6], "%Y-%m-%dT%H:%M:%S")
                        if currentDT > startDT and currentDT < endDT:
                            safety_log.error("Weather warning: " + current_event + " from " + start_time + " to " + end_time )
                            warning_count += 1

        if warning_count > 0:
            status_msg = "Weather warnings detected at " + wx_url
            return False, status_msg
        else:
            return True, "No weather warnings in effect."


class SafetyException(Exception):
    def __init__(self, *args):
        Exception.__init__(self, *args)
