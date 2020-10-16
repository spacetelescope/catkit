import os
import pytest
from requests import HTTPError

from catkit.config import load_config_ini
from catkit.emulators.WebPowerSwitch import WebPowerSwitch


config_filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.ini")
config = load_config_ini(config_filename)


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


@pytest.mark.parametrize("on", (True, False))
@pytest.mark.usefixtures("dummy_config_ini", "dummy_testbed_state")
def test_switch(on):
    switch = WebPowerSwitch(config_id="web_power_switch")
    switch.switch(outlet_id=None, on=on, all=True)


@pytest.mark.parametrize("on", (True, False))
@pytest.mark.usefixtures("dummy_config_ini", "dummy_testbed_state")
def test_switch_lists(on):
    outlet_ids = ("dm1_outlet", "motor_controller_outlet")

    switch = WebPowerSwitch(config_id="web_power_switch")
    switch.switch(outlet_id=outlet_ids, on=on)


def test_outlet_list():
    switch = WebPowerSwitch(config_id="web_power_switch", outlet_list={"switch_1": 1, "switch_2": 2})
    switch.switch(outlet_id="switch_2", on=True)
    switch.turn_on("dm1_outlet")


@pytest.mark.parametrize("status_code", (400, 500))
def test_http_error(status_code):
    switch = WebPowerSwitch(config_id="web_power_switch",
                            outlet_list={"switch_1": 1, "switch_2": 2},
                            status_code=status_code)
    with pytest.raises(HTTPError, match=str(status_code)):
        switch.switch(outlet_id="switch_2", on=True)


@pytest.mark.parametrize("status_code", (100, 300))
def test_runtime_error(status_code):
    switch = WebPowerSwitch(config_id="web_power_switch",
                            outlet_list={"switch_1": 1, "switch_2": 2},
                            status_code=status_code)
    with pytest.raises(RuntimeError, match=str(status_code)):
        switch.switch(outlet_id="switch_2", on=True)
