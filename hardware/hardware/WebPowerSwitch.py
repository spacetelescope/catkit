from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import logging
import requests

from hicat.config import CONFIG_INI
from hicat.interfaces.RemotePowerSwitch import RemotePowerSwitch

"""
Implementation of RemotePowerSwitch abstract base class for the Web Power Switch 7 (LAN controlled power switch).
Example usage:
switch = WebPowerSwitch("web_power_switch")
switch.turn_on("motor_controller_outlet")
"""


class WebPowerSwitch(RemotePowerSwitch):
    log=logging.getLogger(__name__)

    def turn_on(self, outlet_id):
        """
        Turn on an individual outlet.
        """
        outlet_num = CONFIG_INI.getint(self.config_id, outlet_id)
        script_line = self.__find_script_line(outlet_num, True)
        self.__http_script_call(script_line)
        self.log.info("Turning on outlet " + outlet_id + " number " + str(outlet_num))

    def turn_off(self, outlet_id):
        """
        Turn off an individual outlet.
        """
        outlet_num = CONFIG_INI.getint(self.config_id, outlet_id)
        script_line = self.__find_script_line(outlet_num, False)
        self.__http_script_call(script_line)
        self.log.info("Turning off outlet " + outlet_id + " number " + str(outlet_num))

    def all_on(self):
        """
        Turn on all outlets.
        """
        script_line = CONFIG_INI.get(self.config_id, "all_on")
        self.__http_script_call(script_line)
        self.log.info("Turning on all outlets")

    def all_off(self):
        """
        Turn off all outlets.
        """
        script_line = CONFIG_INI.get(self.config_id, "all_off")
        self.__http_script_call(script_line)
        self.log.info("Turning off all outlets")

    @staticmethod
    def __find_script_line(outlet_num, on):
        """
        Returns the script line to execute based on the outlet and the desired state. I added ON and OFF commands for
        each outlet into the script on the power switch.  The logic is as follows:
        1: END
        2: OFF 1
        3: END
        4: ON 1
        5: END
        6: OFF 2
        7: END
        8: ON 2
        9: ...
        :param outlet_num: Integer representing the outlet to control.
        :param on: True for on, False for off.
        :return: Script line number as an integer.
        """
        value = outlet_num * (outlet_num + 1)
        return value + 2 if on else value

    def __http_script_call(self, script_line):
        """
        The power switch interface is actually one long script, and you can tell it to start at any line. I added an
        ON and OFF command for every outlet, followed by an END statement.  The line numbers needed to turn and outlet
        on or off are saved in the ini file.
        :param script_line: integer value for the line of code to start running.
        """
        user, password, ip = self.__get_config_values()
        formatted_script_line = '{num:03d}'.format(num=script_line)
        ip_string = "http://" + ip + "/script?run" + formatted_script_line + "=run"

        try:
            requests.get(ip_string, auth=(user, password))
        except requests.exceptions.RequestException as e:  # This is the correct syntax
            self.log.exception(e.message)

    def __get_config_values(self):
        user = CONFIG_INI.get(self.config_id, "user")
        password = CONFIG_INI.get(self.config_id, "password")
        ip = CONFIG_INI.get(self.config_id, "ip")
        return user, password, ip
