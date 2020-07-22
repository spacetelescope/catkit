import os
import pytest

from hicat.config import CONFIG_INI

from catkit.emulators.ZwoCamera import PoppyZwoEmulator, ZwoCamera
from catkit.config import load_config_ini

data_dir = os.path.join(os.path.dirname(__file__), "data")

# Read, parse, and load CONFIG_INI now so that it is in scope for class attributes initialization,
# i.e., for get_m_per_volt_map()
config_filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.ini")
config = load_config_ini(config_filename)


@pytest.mark.parametrize("config_id", PoppyZwoEmulator.implemented_camera_purposes)
def test_connect(config_id):
    camera_name = CONFIG_INI.get("testbed", "imaging_camera")
    with ZwoCamera(config_id=camera_name) as camera:
        pass
