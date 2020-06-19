import itertools
import os
import pytest

from catkit.config import load_config_ini
from catkit.emulators.WebPowerSwitch import WebPowerSwitch


config_filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.ini")
config = load_config_ini(config_filename)

BOOL_VALUES = (True, False)


@pytest.mark.usefixtures("dummy_config_ini", "dummy_testbed_state")
def test_all_on():
    switch = WebPowerSwitch(config_id="web_power_switch")
    switch.all_on()


@pytest.mark.usefixtures("dummy_config_ini", "dummy_testbed_state")
def test_all_off():
    switch = WebPowerSwitch(config_id="web_power_switch")
    switch.all_off()


@pytest.mark.usefixtures("dummy_config_ini", "dummy_testbed_state")
def test_individual_on():
    switch = WebPowerSwitch(config_id="web_power_switch")
    switch.turn_on("dm1_outlet")


@pytest.mark.usefixtures("dummy_config_ini", "dummy_testbed_state")
def test_individual_off():
    switch = WebPowerSwitch(config_id="web_power_switch")
    switch.turn_off("dm1_outlet")


@pytest.mark.parametrize("on", BOOL_VALUES)
@pytest.mark.usefixtures("dummy_config_ini", "dummy_testbed_state")
def test_switch(on):
    switch = WebPowerSwitch(config_id="web_power_switch")
    switch.switch(outlet_id=None, on=on, all=True)


@pytest.mark.parametrize("on", BOOL_VALUES)
@pytest.mark.usefixtures("dummy_config_ini", "dummy_testbed_state")
def test_switch_lists(on):
    outlet_ids = ("dm1_outlet", "motor_controller_outlet")

    switch = WebPowerSwitch(config_id="web_power_switch")
    switch.switch(outlet_id=outlet_ids, on=on)


def test_outlet_list():
    switch = WebPowerSwitch(config_id="web_power_switch", outlet_list={"switch_1": 1, "switch_2": 2})
    switch.switch(outlet_id="switch_2", on=True)
    switch.turn_on("dm1_outlet")
