import gc

import pytest

from catkit.testbed import devices


@pytest.fixture(scope="function", autouse=False)
def derestricted_device_cache():
    # Setup.
    with devices:
        yield

    with pytest.raises(NameError):
        devices["npoint_a"]
    # Teardown.
    gc.collect()
