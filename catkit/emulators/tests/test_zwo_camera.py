import itertools
import os
import pytest

from hicat.config import CONFIG_INI

from catkit.catkit_types import quantity
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


@pytest.mark.parametrize(("config_id", "exposure_time"),
                         itertools.product(PoppyZwoEmulator.implemented_camera_purposes,
                                           (10, quantity(10, "seconds"))))
def test_capture(config_id, exposure_time):
    camera_name = CONFIG_INI.get("testbed", "imaging_camera")
    with ZwoCamera(config_id=camera_name) as camera:
        camera.take_exposures(exposure_time=exposure_time, num_exposures=2)
