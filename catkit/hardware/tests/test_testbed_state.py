import sys
from types import ModuleType

import pytest


@pytest.fixture(scope="function")
def fake_testbed_state():
    dummy_testbed_state_module = ModuleType("dummy_testbed_state")
    dummy_testbed_state_module.dm1_command_object = 1

    sys.modules[dummy_testbed_state_module.__name__] = dummy_testbed_state_module
    return dummy_testbed_state_module


def test_import(fake_testbed_state):
    import catkit.hardware
    catkit.hardware.load_testbed_state(fake_testbed_state)
    assert catkit.hardware.testbed_state.dm1_command_object == 1


def test_from_import(fake_testbed_state):
    from catkit.hardware import testbed_state, load_testbed_state
    load_testbed_state(fake_testbed_state)
    assert testbed_state.dm1_command_object == 1


def test_identitiy(fake_testbed_state):
    import catkit.hardware
    catkit.hardware.load_testbed_state(fake_testbed_state)
    assert catkit.hardware.testbed_state.self is fake_testbed_state


def test_attribute_identity(fake_testbed_state):
    import catkit.hardware
    catkit.hardware.load_testbed_state(fake_testbed_state)

    catkit.hardware.testbed_state.ref = {}
    assert fake_testbed_state.ref is catkit.hardware.testbed_state.ref


def test_two_way_access(fake_testbed_state):
    import catkit.hardware
    catkit.hardware.load_testbed_state(fake_testbed_state)

    fake_testbed_state.dm1_command_object = 3
    assert catkit.hardware.testbed_state.dm1_command_object == 3

    catkit.hardware.testbed_state.dm1_command_object = 4
    assert fake_testbed_state.dm1_command_object == 4
