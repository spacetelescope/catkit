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


@pytest.fixture()
def dummy_testbed_state(dummy_config_ini):
    # Create dummy testbed_state module
    dummy_testbed_state_module = ModuleType("dummy_testbed_state")

    # Add the required attributes needed for the subsequent tests
    dummy_testbed_state_module.dm1_command_object = None
    dummy_testbed_state_module.dm2_command_object = None

    # Add it to the module cache
    if dummy_testbed_state_module.__name__ not in sys.modules:
        sys.modules[dummy_testbed_state_module.__name__] = dummy_testbed_state_module
    # Load/assign it to catkit.hardware.testbed_state
    catkit.hardware.load_testbed_state(dummy_testbed_state_module)
