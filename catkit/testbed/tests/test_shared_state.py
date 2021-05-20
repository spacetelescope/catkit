import os
import threading
import time
import uuid

from astropy.io import fits
from multiprocess.context import TimeoutError
from multiprocess.managers import BaseProxy, ListProxy, RemoteError
import numpy as np
import pytest

from catkit.testbed.caching import MutexedDict, UserCache
from catkit.multiprocessing import MutexedNamespaceSingleton, Process, SharedMemoryManager, SharedState, SHARED_STATE_ADDRESS


TIMEOUT = 2  # Use a shorter timeout for testing.


@pytest.fixture(scope="function", autouse=True)
def reset_SharedState():
    SharedState.instance = None
    yield
    SharedState.instance = None


def test_naked_shared_state():
    def client1_func():
        manager = SharedMemoryManager(address=SHARED_STATE_ADDRESS)
        manager.connect()
        shared_state = manager.SharedState()

        assert shared_state.attribute_from_parent == "from parent"

        shared_state.attribute_from_client1 = "from client1"
        shared_state.attribute_from_parent = "mutated from client1"

    def client2_func():
        manager = SharedMemoryManager(address=SHARED_STATE_ADDRESS)
        manager.connect()
        shared_state = manager.SharedState()

        assert shared_state.attribute_from_client1 == "from client1"
        assert shared_state.attribute_from_parent == "mutated from client1"

        shared_state.attribute_from_client2 = "from client2"

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS) as manager:
        client1 = Process(target=client1_func)
        client2 = Process(target=client2_func)

        shared_state = manager.SharedState()
        shared_state.attribute_from_parent = "from parent"

        client1.start()
        client1.join()

        client2.start()
        client2.join()

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

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS):
        client1 = Process(target=client1_func)
        client2 = Process(target=client2_func)

        shared_state = SharedState()

        shared_state.attribute_from_parent = "from parent"

        client1.start()
        client1.join()

        client2.start()
        client2.join()

        assert shared_state.attribute_from_client1 == "from client1"
        assert shared_state.attribute_from_client2 == "from client2"
        assert shared_state.attribute_from_parent == "mutated from client1"


# def test_shutdown():
#     shared_state = SharedState()
#     server_pid = shared_state._manager.getpid()
#     assert server_pid in [process.pid for process in psutil.process_iter()]
#
#     del shared_state
#     time.sleep(0.5)
#     assert server_pid not in [process.pid for process in psutil.process_iter()]


def test_mutex_timeout():
    def client1_func(barrier):
        shared_state = SharedState()
        assert isinstance(shared_state, BaseProxy)
        with shared_state as lock_acquired:
            assert lock_acquired is True
            barrier.wait()
            time.sleep(TIMEOUT*2)  # Acquire lock for longer than the (default) timeout on client2.

    def client2_func(barrier):
        shared_state = SharedState()
        assert isinstance(shared_state, BaseProxy)
        barrier.wait()
        with pytest.raises((RemoteError, TimeoutError), match="Failed to acquire lock"):
            with shared_state:
                pass

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS) as manager:
        barrier = manager.get_barrier("test_mutex_timeout", 2)

        client1 = Process(target=client1_func, args=(barrier,))
        client2 = Process(target=client2_func, args=(barrier,))
        shared_state = SharedState()

        client1.start()
        client2.start()

        client1.join()
        client2.join()


def test_mutex_timeout2():
    def client1_func():
        shared_state = SharedState()
        with pytest.raises((RemoteError, TimeoutError), match="Failed to acquire lock"):
            shared_state.from_client = 1

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS):
        with SharedState():
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

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS):
        client1 = Process(target=client1_func)
        client2 = Process(target=client2_func)
        shared_state = SharedState()

        client1.start()
        client2.start()

        client1.join()
        client2.join()

        assert shared_state.client1 == 1
        assert shared_state.client2 == 2


class MyCache(UserCache):
    def load(self, key, *args, **kwargs):
        self.data[key] = f"auto populated_{os.getpid()}_{uuid.uuid4()}"


SharedMemoryManager.register("MyCache", callable=MyCache, proxytype=MyCache.Proxy)


def test_UserCache():

    def client_func(item_from_parent):
        shared_state = SharedState()
        auto_loaded_from_parent = shared_state.my_cache["new_from_parent"]
        assert auto_loaded_from_parent == item_from_parent, f"{auto_loaded_from_parent}, {item_from_parent}"

        assert shared_state.my_cache["from_parent"] == 56789

        # Test auto load from client.
        auto_loaded_from_client = shared_state.my_cache["new_from_client"]
        assert f"auto populated_{shared_state._manager.getpid()}" in auto_loaded_from_client
        assert auto_loaded_from_parent != auto_loaded_from_client
        shared_state.my_cache["from_client"] = 1234

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS):
        shared_state = SharedState()
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


def test_get_mutex():
    def client_func():
        shared_state = SharedState()
        with pytest.raises((RemoteError, TimeoutError), match="Failed to acquire lock"):
            assert shared_state.from_parent == 567899

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS):
        shared_state = SharedState()
        mutex = shared_state.get_mutex()
        assert isinstance(mutex, BaseProxy)
        with mutex:
            shared_state.from_parent = 567899

            client = Process(target=client_func)
            client.start()
            client.join()

        with shared_state:
            client = Process(target=client_func)
            client.start()
            client.join()

        with mutex:
            with shared_state:
                client = Process(target=client_func)
                client.start()
                client.join()


def test_MutexedCache():
    def client_func():
        shared_state = SharedState()

        with shared_state.my_cache:
            assert shared_state.my_cache["from_parent"] == 56789
            with shared_state.my_cache:  # Might as well test the re-entrant-ness.
                shared_state.my_cache["from_client"] = 1234

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS):
        shared_state = SharedState()    # Instantiate an instance of MyCache on the server and assign its proxy to SharedState.my_cache to access from
        # any client.
        assert isinstance(shared_state, BaseProxy)

        mutexed_dict = shared_state._manager.MutexedDict()
        assert isinstance(mutexed_dict, BaseProxy)
        assert mutexed_dict._manager

        # Now pass this to the server - which you can't actually do since we're passing a proxy back and not all of it,
        # i.e., ``_manager`` gets stripped out as it's not pickleble.
        shared_state.my_cache = mutexed_dict
        assert isinstance(shared_state.my_cache, BaseProxy)
        assert shared_state.my_cache._id == mutexed_dict._id
        assert shared_state.my_cache is not mutexed_dict

        # Manager has now been stripped. The consequence of this is that no proxy can be returned from ``my_cache`` as
        # it has no manager from which to build one.
        assert not shared_state.my_cache._manager

        with shared_state.my_cache:
            shared_state.my_cache["from_parent"] = 56789

        client = Process(target=client_func)
        client.start()
        client.join()

        assert shared_state.my_cache["from_client"] == 1234


def test_thread_safety_MutexedCache_timeout():
    def client_func(cache, barrier):
        with cache:
            barrier.wait()
            cache["from child"] = 12345
            time.sleep(TIMEOUT*2)

    cache = MutexedDict(timeout=TIMEOUT)

    barrier = threading.Barrier(parties=2)
    client = threading.Thread(target=client_func, args=(cache, barrier))
    client.start()
    barrier.wait()

    with pytest.raises(TimeoutError, match="Failed to acquire lock"):
        assert cache["from child"] == 12345
    client.join()


def test_MutexedCache_timeout():
    def client_func():
        shared_state = SharedState()
        with pytest.raises((RemoteError, TimeoutError), match="Failed to acquire lock"):
            shared_state.my_cache["from_client"] = 1234

        with pytest.raises((RemoteError, TimeoutError), match="Failed to acquire lock"):
            with shared_state.my_cache:
                pass

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS):
        shared_state = SharedState()    # Instantiate an instance of MyCache on the server and assign its proxy to SharedState.my_cache to access from
        # any client.
        shared_state.my_cache = shared_state._manager.MutexedDict(timeout=TIMEOUT)
        with shared_state.my_cache:
            shared_state.my_cache["from_parent"] = 56789

            client = Process(target=client_func)
            client.start()
            client.join()


def test_normal_dict_update():
    with SharedMemoryManager(address=SHARED_STATE_ADDRESS):
        shared_state = SharedState()
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

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS):
        shared_state = SharedState()
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
    with SharedMemoryManager(address=SHARED_STATE_ADDRESS):
        shared_state = SharedState()
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


# The following test the design pattern used for both hicat's sim and testbed-state objects.

class HicatTestbedState(MutexedNamespaceSingleton):
    instance = None

    address = SHARED_STATE_ADDRESS
    timeout = TIMEOUT

    def __init__(self, *args, **kwargs):
        if object.__getattribute__(self, "__class__").instance is None:
            super().__init__(*args, **kwargs)
            self.background_cache = MutexedDict(lock=self.get_mutex())
            self.mode = None
            self.nested_dic = MutexedDict(lock=self.get_mutex())

    def get_background_cache(self):
        return self.background_cache

    def get_nested_dic(self):
        return self.nested_dic

    @property
    def background_cache(self):
        return self._background_cache

    @background_cache.setter
    def background_cache(self, value):
        self._background_cache = value
        # # Clobber existing mutex with that of the parent namespace such that when its proxy is returned it is
        # # still mutexed (by the parent) even if it's referenced from beyond the parent namespace.
        #self._background_cache._catkit_mutex = self.get_mutex()

    @property
    def pid(self):
        return os.getpid()

    class Proxy(MutexedNamespaceSingleton.Proxy):
        _method_to_typeid_ = {}
        if hasattr(MutexedNamespaceSingleton.Proxy, "_method_to_typeid_"):
            _method_to_typeid_.update(MutexedNamespaceSingleton.Proxy._method_to_typeid_)
        _method_to_typeid_.update({"get_background_cache": "MutexedDictProxy",
                                   "get_nested_dic": "NestedMutexedDictProxy"})

        def get_background_cache(self):
            return self._callmethod("get_background_cache")

        def get_nested_dic(self):
            return self._callmethod("get_nested_dic")

        @property
        def background_cache(self):
            ret = self.get_background_cache()
            assert isinstance(ret, BaseProxy)
            return ret

        @property
        def nested_dic(self):
            return self.get_nested_dic()


SharedMemoryManager.register(HicatTestbedState.__name__, callable=HicatTestbedState, proxytype=HicatTestbedState.Proxy, create_method=True)


@pytest.fixture(scope="function", autouse=False)
def reset_HicatTestbedState():
    HicatTestbedState.instance = None
    yield
    HicatTestbedState.instance = None


def test_TestbedState(reset_HicatTestbedState):

    def client1_func():
        shared_state = HicatTestbedState()
        assert isinstance(shared_state, BaseProxy)

        with shared_state:
            assert shared_state.mode == "initial mode", shared_state.mode
            shared_state.mode = "client1 mode"
            assert shared_state.mode == "client1 mode"

            assert isinstance(shared_state.background_cache, BaseProxy)
            #with background_cache:
            shared_state.background_cache["from client 1"] = 12345
            assert shared_state.background_cache["from client 1"] == 12345

    def client2_func():
        shared_state = HicatTestbedState()
        with shared_state:
            assert shared_state.mode == "client1 mode", shared_state.mode

            assert shared_state.background_cache["from client 1"] == 12345

            shared_state.background_cache["from client 2"] = 6789
            assert shared_state.background_cache["from client 2"] == 6789

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS) as manager:
        shared_state = HicatTestbedState()
        assert isinstance(shared_state, BaseProxy)
        assert shared_state.get_mutex().timeout == TIMEOUT
        assert shared_state.background_cache.get_mutex().timeout == TIMEOUT

        assert shared_state.mode is None
        shared_state.mode = "initial mode"
        assert shared_state.mode == "initial mode"

        assert shared_state.pid == manager.getpid()
        assert shared_state.pid != os.getpid()

        client1 = Process(target=client1_func)
        client2 = Process(target=client2_func)

        client1.start()
        time.sleep(0.5)
        client2.start()

        client1.join()
        client2.join()

        assert shared_state.mode == "client1 mode"
        assert isinstance(shared_state.background_cache, BaseProxy)
        assert shared_state.background_cache["from client 1"] == 12345
        assert shared_state.background_cache["from client 2"] == 6789

        # Test that proxy setter is not required (weak test without spawning another client process).
        shared_state.background_cache = shared_state._manager.MutexedDict({1: 345}, timeout=TIMEOUT)
        cache = shared_state.background_cache
        assert cache[1] == 345
        background_cache = shared_state.get_background_cache()
        assert isinstance(background_cache, BaseProxy)
        assert background_cache[1] == 345


def test_co_mutex(reset_HicatTestbedState):
    def client1_func():
        shared_state = HicatTestbedState()
        with shared_state:
            manager.get_barrier("mutex_acquired_from_client", 2).wait()
            time.sleep(TIMEOUT*5)

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS) as manager:
        shared_state = HicatTestbedState()
        assert shared_state.get_mutex().timeout == TIMEOUT

        background_cache = shared_state.background_cache

        assert background_cache.get_mutex() == shared_state.nested_dic.get_mutex()
        assert background_cache.get_mutex() == shared_state.get_mutex()
        assert background_cache.get_mutex().timeout == TIMEOUT

        client1 = Process(target=client1_func)
        client1.start()
        manager.get_barrier("mutex_acquired_from_client", 2).wait()
        with pytest.raises((RemoteError, TimeoutError), match="Failed to acquire lock"):
            background_cache["test"] = 2

        client1.join()


def test_access_time(reset_HicatTestbedState):
    with SharedMemoryManager(address=SHARED_STATE_ADDRESS) as manager:
        shared_state = HicatTestbedState()

        n = 50

        t0_all = time.time()
        for i in range(n):
            t0 = time.time()
            #shared_state.background_cache[i] = i
            shared_state.m = i
            t_set = time.time()
            #shared_state.background_cache[i]
            shared_state.m
            t_get = time.time()

            t_exp_set = (t_set - t0)*1e6
            t_exp_get = (t_get - t_set)*1e6
            print(i, t_exp_set, t_exp_get)
        t_all = (time.time() - t0_all)*1e6
        print("total (us)", t_all, t_all/n)
        mean_time = t_all/n
        limit = 600  # Adhoc.
        assert mean_time < 600, f"mean rt for sequential set & get: {mean_time} < {limit}"
        #assert False


def test_nested_dict(reset_HicatTestbedState):
    def client_func():
        shared_state = HicatTestbedState()
        assert shared_state.nested_dic["from parent"]._getvalue() == {1: 1, 2: 2}
        shared_state.nested_dic["from parent"][1] = 3

    with SharedMemoryManager(address=SHARED_STATE_ADDRESS) as manager:
        shared_state = HicatTestbedState()
        assert isinstance(shared_state.nested_dic, BaseProxy)

        nested_dic = shared_state.nested_dic
        nested_dic["from parent"] = manager.MutexedDict({1: 1, 2: 2})

        client = Process(target=client_func)
        client.start()
        client.join()

        assert nested_dic["from parent"][1] == 3
