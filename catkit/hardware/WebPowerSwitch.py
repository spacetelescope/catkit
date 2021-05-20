from collections.abc import Iterable
import logging
import requests

import catkit.util
from catkit.config import CONFIG_INI
from catkit.interfaces.RemotePowerSwitch import RemotePowerSwitch

"""
Implementation of RemotePowerSwitch abstract base class for the Web Power Switch 7 (LAN controlled power switch).
Example usage:
switch = WebPowerSwitch("web_power_switch")
switch.turn_on("motor_controller_outlet")
"""


class WebPowerSwitch(RemotePowerSwitch):

    instrument_lib = requests

    def initialize(self, user=None, password=None, ip=None, outlet_list={}):
        self.log = logging.getLogger()

        # Given the specificity of the script numbering I'm not sure that it really makes sense
        # to pass in these values, but hey.
        self.user = CONFIG_INI.get(self.config_id, "user") if user is None else user
        self.password = CONFIG_INI.get(self.config_id, "password") if password is None else password
        self.ip = CONFIG_INI.get(self.config_id, "ip") if ip is None else ip

        self.outlet_list = outlet_list

        # Obtain only from config for simplicity.
        self.all_off_id = CONFIG_INI.getint(self.config_id, "all_off")
        self.all_on_id = CONFIG_INI.getint(self.config_id, "all_on")

    def _open(self):
        pass

    def _close(self):
        pass

    def switch(self, outlet_id, on, all=False):
        """ Turn on/off all/individual outlet(s).
        :param outlet_id: str or iterable of str, representing the config id name(s) of the outlet(s).
        :param on: bool, switch action.
        :param all: bool, switch all outlets
        """
        if all:
            self.all_on() if on else self.all_off()
        else:
            outlet_ids = outlet_id if isinstance(outlet_id, Iterable) and not isinstance(outlet_id, str) else [outlet_id]
            for id in outlet_ids:
                self.turn_on(id) if on else self.turn_off(id)

    def turn_on(self, outlet_id):
        """ Turn on an individual outlet. """
        outlet_num = self.outlet_list[outlet_id] if outlet_id in self.outlet_list else CONFIG_INI.getint(self.config_id, outlet_id)
        script_line = self._find_script_line(outlet_num, on=True)
        self._http_script_call(script_line)
        self.log.info("Turning on outlet " + outlet_id + " number " + str(outlet_num))

    def turn_off(self, outlet_id):
        """ Turn off an individual outlet. """
        outlet_num = self.outlet_list[outlet_id] if outlet_id in self.outlet_list else CONFIG_INI.getint(self.config_id, outlet_id)
        script_line = self._find_script_line(outlet_num, on=False)
        self._http_script_call(script_line)
        self.log.info("Turning off outlet " + outlet_id + " number " + str(outlet_num))

    def all_on(self):
        """ Turn on all outlets. """
        self._http_script_call(self.all_on_id)
        self.log.info("Turning on all outlets")

    def all_off(self):
        """ Turn off all outlets. """
        self._http_script_call(self.all_off_id)
        self.log.info("Turning off all outlets")

    @staticmethod
    def _find_script_line(outlet_num, on):
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
        value = outlet_num * 4
        return value if on else value - 2

    def _http_script_call(self, script_line):
        """
        The power switch interface is actually one long script, and you can tell it to start at any line. I added an
        ON and OFF command for every outlet, followed by an END statement.  The line numbers needed to turn and outlet
        on or off are saved in the ini file.
        :param script_line: integer value for the line of code to start running.
        """
        formatted_script_line = f'{script_line:03d}'
        ip_string = f"http://{self.ip}/script?run{formatted_script_line}=run"

        resp = self.instrument_lib.get(ip_string, auth=(self.user, self.password))
        # Raise an error if one occurred.
        resp.raise_for_status()
        # Now be explicit to catch some non HTTP errors status that we also don't want to deal with.
        if resp.status_code != 200:
            raise RuntimeError(f"{self.config_id} error: GET returned {resp.status_code} when 200 was expected.")
        catkit.util.sleep(1)  # NOTE: This needs to match or exceed that set in the switch's web setup. See CATKIT-53.
