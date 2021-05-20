import gc
import os

import pytest

from catkit.emulators.npoint_tiptilt import SimNPointLC400
from catkit.testbed import devices
from catkit.testbed.caching import DeviceCacheEnum, SharedSingletonDeviceCache
import catkit.util
from catkit.multiprocessing import EXCEPTION_SERVER_ADDRESS, SharedMemoryManager

catkit.util.simulation = True


def pytest_configure(config):
    config.addinivalue_line("markers", "dont_own_exception_handler: Neither start nor shutdown the exception handler server.")


@pytest.fixture(scope="function", autouse=False)
def derestricted_device_cache():
    # Setup.
    with devices:
        yield

    with pytest.raises(NameError):
        devices["npoint_a"]
    # Teardown.
    gc.collect()


@pytest.fixture(scope="function", autouse=True)
def exception_handler(request):
    if "dont_own_exception_handler" not in request.keywords:
        with SharedMemoryManager(address=EXCEPTION_SERVER_ADDRESS):
            yield
    else:
        yield
