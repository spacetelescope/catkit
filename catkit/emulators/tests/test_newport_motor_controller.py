import os

import pytest

from catkit.emulators.newport.NewportMotorController import NewportMotorControllerEmulator
import catkit.hardware.newport.NewportMotorController
from catkit.interfaces.Instrument import SimInstrument

from catkit.config import load_config_ini

data_dir = os.path.join(os.path.dirname(__file__), "data")

# Read, parse, and load CONFIG_INI now so that it is in scope for class attributes initialization,
# i.e., for get_m_per_volt_map()
config_filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.ini")
config = load_config_ini(config_filename)


class NewportMotorController(SimInstrument, catkit.hardware.newport.NewportMotorController.NewportMotorController):
    instrument_lib = NewportMotorControllerEmulator


@pytest.mark.usefixtures("dummy_config_ini")
def test_initialize_to_nominal():
    from catkit.config import CONFIG_INI
    with NewportMotorController(config_id="dummy", host="dummy", port="dummy", test_initialize_to_nominal=True) as mc:
        motors = [s for s in CONFIG_INI.sections() if s.startswith('motor_')]
        for motor_id in motors:
            assert mc.get_position(motor_id) == CONFIG_INI.getfloat(motor_id, "nominal")


@pytest.mark.usefixtures("dummy_config_ini")
def test_abolute_move():
    with NewportMotorController(config_id="dummy", host="dummy", port="dummy") as mc:
        motor_id = "motor_FPM_X"
        position = mc.get_position(motor_id)
        new_position = position + 2.
        mc.absolute_move(motor_id, new_position)
        assert mc.get_position(motor_id) == new_position


@pytest.mark.usefixtures("dummy_config_ini")
def test_relative_move():
    with NewportMotorController(config_id="dummy", host="dummy", port="dummy") as mc:
        motor_id = "motor_FPM_X"
        position = mc.get_position(motor_id)
        mc.relative_move(motor_id, 2.)
        assert mc.get_position(motor_id) == position + 2.
