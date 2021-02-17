import os
import sys
from types import ModuleType

import pytest

import catkit.config


@pytest.fixture()
def dummy_config_ini():
    config_filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.ini")
    config = catkit.config.load_config_ini(config_filename)
    catkit.config.CONFIG_INI.point_to(config)
