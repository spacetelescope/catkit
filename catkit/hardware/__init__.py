import importlib

from catkit.catkit_types import Pointer

testbed_state = Pointer(None)


def load_testbed_state(module_to_load):
    global testbed_state

    testbed_state_to_load = importlib.import_module(module_to_load) if isinstance(module_to_load, str) else module_to_load
    testbed_state.point_to(testbed_state_to_load)
    print(f"'catkit.hardware.testbed_state' now points to '{module_to_load}'")
