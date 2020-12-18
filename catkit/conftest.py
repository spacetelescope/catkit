import gc

import pytest

import catkit.testbed


@pytest.fixture(scope="function", autouse=False)
def derestricted_device_cache():
    # Setup.
    with catkit.testbed.devices:
        yield

    with pytest.raises(NameError):
        catkit.testbed.devices["npoint_a"]
    # Teardown.
    gc.collect()
