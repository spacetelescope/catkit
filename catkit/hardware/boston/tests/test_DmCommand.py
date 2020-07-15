import numpy as np
import pytest

from catkit.config import CONFIG_INI
from catkit.hardware.boston.DmCommand import DmCommand

number_of_actuators = 952
command_length = 2048
max_voltage = 200

dm1_bias_voltage = CONFIG_INI.getint('boston_kilo952', 'bias_volts_dm1')
dm2_bias_voltage = CONFIG_INI.getint('boston_kilo952', 'bias_volts_dm2')


@pytest.mark.parametrize("bias", (False, 123))
def test_non_config_bias_voltages(bias):
    dm1 = DmCommand(np.zeros(number_of_actuators), dm_num=1, bias=bias).to_dm_command()[:number_of_actuators]*max_voltage
    dm2 = DmCommand(np.zeros(number_of_actuators), dm_num=2, bias=bias).to_dm_command()[command_length//2:command_length//2+number_of_actuators]*max_voltage

    if bias is False:
        assert np.allclose(dm1, 0)
        assert np.allclose(dm2, 0)
    else:
        assert np.allclose(dm1, bias)
        assert np.allclose(dm2, bias)


@pytest.mark.parametrize("bias", (None, True))
def test_config_bias_voltages(bias):
    dm1 = DmCommand(np.zeros(number_of_actuators), dm_num=1, bias=bias).to_dm_command()[:number_of_actuators]*max_voltage
    dm2 = DmCommand(np.zeros(number_of_actuators), dm_num=2, bias=bias).to_dm_command()[command_length//2:command_length//2+number_of_actuators]*max_voltage

    if bias is None or bias is True:
        assert np.allclose(dm1, dm1_bias_voltage)
        assert np.allclose(dm2, dm2_bias_voltage)
    else:
        assert False
