import os
import psutil
import time
import uuid

from astropy.io import fits
from multiprocess.context import TimeoutError
from multiprocess.managers import ListProxy
import numpy as np
import pytest

from catkit.testbed.caching import SharedState, UserCache
from catkit.multiprocessing import Process, SharedMemoryManager

TIMEOUT = 5  # Use a shorter timeout for testing.


def test_naked_shared_state():
    def client1_func():
        manager = SharedMemoryManager()
        manager.connect()
        shared_state = manager.SharedState()

        assert shared_state.attribute_from_parent == "from parent"

        shared_state.attribute_from_client1 = "from client1"
        shared_state.attribute_from_parent = "mutated from client1"

    def client2_func():
        manager = SharedMemoryManager()
        manager.connect()
        shared_state = manager.SharedState()

        assert shared_state.attribute_from_client1 == "from client1"
        assert shared_state.attribute_from_parent == "mutated from client1"

        shared_state.attribute_from_client2 = "from client2"

    with SharedMemoryManager() as manager:
        client1 = Process(target=client1_func)
        client2 = Process(target=client2_func)

        shared_state = manager.SharedState()
        shared_state.attribute_from_parent = "from parent"

        client1.start()
        client1.join()

        client2.start()
        client2.join()

        print(shared_state.attribute_from_client1, shared_state.attribute_from_client2,shared_state.attribute_from_parent)

        assert shared_state.attribute_from_client1 == "from client1"
        assert shared_state.attribute_from_client2 == "from client2"
        assert shared_state.attribute_from_parent == "mutated from client1"


def test_SharedState():
    def client1_func():
        shared_state = SharedState()

        assert shared_state.attribute_from_parent == "from parent"

        shared_state.attribute_from_client1 = "from client1"
        shared_state.attribute_from_parent = "mutated from client1"

    def client2_func():
        shared_state = SharedState()

        assert shared_state.attribute_from_client1 == "from client1"
        assert shared_state.attribute_from_parent == "mutated from client1"

        shared_state.attribute_from_client2 = "from client2"

    client1 = Process(target=client1_func)
    client2 = Process(target=client2_func)

    shared_state = SharedState(own=True)

    shared_state.attribute_from_parent = "from parent"

    client1.start()
    client1.join()

    client2.start()
    client2.join()

    assert shared_state.attribute_from_client1 == "from client1"
    assert shared_state.attribute_from_client2 == "from client2"
    assert shared_state.attribute_from_parent == "mutated from client1"


def test_shutdown():
    shared_state = SharedState(own=True)
    server_pid = shared_state._manager.getpid()
    assert server_pid in [process.pid for process in psutil.process_iter()]

    del shared_state
    time.sleep(0.5)
    assert server_pid not in [process.pid for process in psutil.process_iter()]


def test_mutex_timeout():
    def client1_func():
        shared_state = SharedState()
        with shared_state:
            time.sleep(TIMEOUT*1.5)  # Acquire lock for longer than the (default) timeout on client2.

    def client2_func():
        shared_state = SharedState()
        with pytest.raises(TimeoutError):
            with shared_state:
                pass

    client1 = Process(target=client1_func)
    client2 = Process(target=client2_func)
    shared_state = SharedState(own=True, timeout=TIMEOUT)

    client1.start()
    time.sleep(0.5)  # Sleep to help client 1 acquire the lock 1st.
    client2.start()

    client1.join()
    client2.join()


def test_mutex_timeout2():
    def client1_func():
        shared_state = SharedState()
        with pytest.raises(TimeoutError):
            shared_state.from_client = 1

    shared_state = SharedState(own=True, timeout=TIMEOUT)

    with shared_state:
        client1 = Process(target=client1_func)
        client1.start()
        client1.join()


def test_mutex():
    def client1_func():
        shared_state = SharedState()
        with shared_state:
            shared_state.client1 = 1
            time.sleep(TIMEOUT/4)

    def client2_func():
        shared_state = SharedState()
        with shared_state:
            shared_state.client2 = 2

    client1 = Process(target=client1_func)
    client2 = Process(target=client2_func)
    shared_state = SharedState(own=True)

    client1.start()
    client2.start()

    client1.join()
    client2.join()

    assert shared_state.client1 == 1
    assert shared_state.client2 == 2


def test_UserCache():
    class MyCache(UserCache):
        def load(self, key, *args, **kwargs):
            self.data[key] = f"auto populated_{os.getpid()}_{uuid.uuid4()}"

    SharedMemoryManager.register("MyCache", callable=MyCache, proxytype=MyCache.Proxy)

    def client_func(item_from_parent):
        shared_state = SharedState(own=False)
        auto_loaded_from_parent = shared_state.my_cache["new_from_parent"]
        assert auto_loaded_from_parent == item_from_parent, f"{auto_loaded_from_parent}, {item_from_parent}"

        assert shared_state.my_cache["from_parent"] == 56789

        # Test auto load from client.
        auto_loaded_from_client = shared_state.my_cache["new_from_client"]
        assert f"auto populated_{shared_state._manager.getpid()}" in auto_loaded_from_client
        assert auto_loaded_from_parent != auto_loaded_from_client
        shared_state.my_cache["from_client"] = 1234

    shared_state = SharedState(own=True)
    # Instantiate an instance of MyCache on the server and assign its proxy to SharedState.my_cache to access from
    # any client.
    shared_state.my_cache = shared_state._manager.MyCache()
    shared_state.my_cache["from_parent"] = 56789

    # Test auto load from parent.
    auto_loaded_from_parent = shared_state.my_cache["new_from_parent"]
    assert f"auto populated_{shared_state._manager.getpid()}" in auto_loaded_from_parent

    client = Process(target=client_func, args=(auto_loaded_from_parent,))
    client.start()
    client.join()

    assert f"auto populated_{shared_state._manager.getpid()}" in shared_state.my_cache["new_from_client"]
    assert shared_state.my_cache["new_from_client"] != auto_loaded_from_parent
    assert shared_state.my_cache["from_client"] == 1234


def test_MutexedCache():
    def client_func():
        shared_state = SharedState()

        with shared_state.my_cache:
            assert shared_state.my_cache["from_parent"] == 56789
            with shared_state.my_cache:  # Might as well test the re-entrant-ness.
                shared_state.my_cache["from_client"] = 1234

    shared_state = SharedState(own=True)
    # Instantiate an instance of MyCache on the server and assign its proxy to SharedState.my_cache to access from
    # any client.
    shared_state.my_cache = shared_state._manager.MutexedCache()
    with shared_state.my_cache:
        shared_state.my_cache["from_parent"] = 56789

    client = Process(target=client_func)
    client.start()
    client.join()

    assert shared_state.my_cache["from_client"] == 1234


def test_MutexedCache_timeout():
    def client_func():
        shared_state = SharedState()
        with pytest.raises(TimeoutError):
            shared_state.my_cache["from_client"] = 1234

        with pytest.raises(TimeoutError):
            with shared_state.my_cache:
                pass

    shared_state = SharedState(own=True)
    # Instantiate an instance of MyCache on the server and assign its proxy to SharedState.my_cache to access from
    # any client.
    shared_state.my_cache = shared_state._manager.MutexedCache(timeout=TIMEOUT)
    with shared_state.my_cache:
        shared_state.my_cache["from_parent"] = 56789

        client = Process(target=client_func)
        client.start()
        client.join()


def test_normal_dict_update():
    shared_state = SharedState(own=True)
    shared_state.my_dict = {}
    shared_state.my_dict["item_1"] = 1
    assert shared_state.my_dict.get("item_1") is None

    shared_state.my_dict = shared_state._manager.dict()
    shared_state.my_dict["item_1"] = 1
    assert shared_state.my_dict["item_1"] == 1


def test_image_transfer():
    shape = (4096, 4096)

    def client_func(image_from_parent):
        shared_state = SharedState()
        assert shared_state.image_from_parent.data.shape == shape
        assert np.allclose(shared_state.image_from_parent.data, image_from_parent.data)

    shared_state = SharedState(own=True)
    image = fits.PrimaryHDU(data=np.random.rand(*shape))
    shared_state.image_from_parent = image

    client = Process(target=client_func, args=(image,))
    client.start()
    client.join()


def test_hdu_list_update():
    shape = (4096, 4096)

    def client_func():
        shared_state = SharedState()
        image_list = shared_state.nested_image_list
        assert len(image_list) == 2, len(image_list)
        assert image_list[0].data.shape == shape
        assert image_list[1].data.shape == tuple([n//2 for n in shape])

    SharedMemoryManager.register("HDUList", callable=fits.HDUList, proxytype=ListProxy)
    shared_state = SharedState(own=True)

    # The following will fail to update the HDUList on the server.
    shared_state.broken_nested_image_list = fits.HDUList()
    shared_state.broken_nested_image_list.append(fits.PrimaryHDU(data=np.random.rand(*shape)))
    assert len(shared_state.broken_nested_image_list) == 0

    # However, it'll work if you "put it back".
    hdu_list = shared_state.broken_nested_image_list
    hdu_list.append(fits.PrimaryHDU(data=np.random.rand(*shape)))
    shared_state.broken_nested_image_list = hdu_list
    assert len(shared_state.broken_nested_image_list) == 1

    # The following will get updated.
    shared_state.nested_image_list = shared_state._manager.HDUList()
    shared_state.nested_image_list.append(fits.PrimaryHDU(data=np.random.rand(*shape)))
    shared_state.nested_image_list.append(fits.PrimaryHDU(data=np.random.rand(*[n//2 for n in shape])))
    assert len(shared_state.nested_image_list) == 2

    # However, nesting is inevitable and thus so are failed updates, e.g., the header will not...
    shared_state.nested_image_list[0].header["my key"] = "updated"
    assert shared_state.nested_image_list[0].header.get("my key") is None

    client = Process(target=client_func)
    client.start()
    client.join()


class TestbedState(SharedState):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self._own:
            with self:
                self.background_cache = self._manager.dict()
                self.mode = None

    @property  # Belongs to the proxy so gets executed locally, i.e., the same process as the caller.
    def pid(self):
        return os.getpid()


def test_TestbedState():

    def client1_func():
        shared_state = TestbedState()
        with shared_state:
            assert shared_state.mode == "initial mode", shared_state.mode
            shared_state.mode = "client1 mode"
            assert shared_state.mode == "client1 mode"

            shared_state.background_cache["from client 1"] = 12345
            assert shared_state.background_cache["from client 1"] == 12345

            assert shared_state.pid == os.getpid()
            assert shared_state.pid != shared_state._manager.getpid()

    def client2_func():
        shared_state = TestbedState()
        with shared_state:
            assert shared_state.mode == "client1 mode", shared_state.mode

            assert shared_state.background_cache["from client 1"] == 12345

            shared_state.background_cache["from client 2"] = 6789
            assert shared_state.background_cache["from client 2"] == 6789

            assert shared_state.pid == os.getpid()
            assert shared_state.pid != shared_state._manager.getpid()

    shared_state = TestbedState(own=True)
    assert shared_state.mode is None
    shared_state.mode = "initial mode"
    assert shared_state.mode == "initial mode"

    assert shared_state.pid == os.getpid()
    assert shared_state.pid != shared_state._manager.getpid()

    client1 = Process(target=client1_func)
    client2 = Process(target=client2_func)

    client1.start()
    time.sleep(0.5)
    client2.start()

    client1.join()
    client2.join()

    assert shared_state.mode == "client1 mode"
    assert shared_state.background_cache["from client 1"] == 12345
    assert shared_state.background_cache["from client 2"] == 6789


if __name__ == "__main__":
    test_TestbedState()

