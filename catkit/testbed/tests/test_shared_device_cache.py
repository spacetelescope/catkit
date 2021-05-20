import os

import multiprocess
from multiprocess.context import TimeoutError
from multiprocess.managers import BaseProxy, RemoteError
import pytest
import threading
import time

from catkit.emulators.npoint_tiptilt import SimNPointLC400
from catkit.multiprocessing import MutexedNamespace, Process, SharedMemoryManager
from catkit.testbed.caching import DeviceCache, DeviceCacheEnum, SharedSingletonDeviceCache


TIMEOUT = 2


def test_mutexed_instrument():
    def thread_func(dev):
        mutex = dev.get_mutex()
        with mutex:
            dev.a = 3
            time.sleep(mutex.timeout*2)

    dev = SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)
    assert hasattr(dev, "_catkit_mutex")
    assert dev.get_mutex().timeout == TIMEOUT

    thread = threading.Thread(target=thread_func, args=(dev,))
    thread.start()
    with pytest.raises(TimeoutError, match="Failed to acquire lock"):
        assert dev.a == 3
    thread.join()


# def test_OwnedContext():
#     dev = SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)
#     assert hasattr(dev, "_catkit_mutex")
#
#     new = type(dev).__new__(type(dev))
#
#     assert hasattr(new, "_catkit_mutex"), type(dev).__mro__
#
#     owned_dev = DeviceCache.OwnedContext(dev)
#     assert hasattr(owned_dev._owned_obj, "_catkit_mutex")


def test_singleton_independence():
    class DeviceCacheA(SharedSingletonDeviceCache):
        instance = None
        callbacks = {}
        aliases = {}

    class DeviceCacheB(SharedSingletonDeviceCache):
        instance = None
        callbacks = {}
        aliases = {}

    @DeviceCacheA.link(key="a")
    def foo():
        pass

    @DeviceCacheB.link(key="b")
    def bar():
        pass

    assert "a" in DeviceCacheA.callbacks
    assert "b" in DeviceCacheB.callbacks

    assert "b" not in DeviceCacheA.callbacks
    assert "a" not in DeviceCacheB.callbacks

    assert DeviceCacheA() is DeviceCacheA()
    assert DeviceCacheA() is not DeviceCacheB()

    assert DeviceCacheA.callbacks is DeviceCacheA().callbacks
    assert "a" in DeviceCacheA().callbacks
    assert "b" in DeviceCacheB().callbacks

    assert "b" not in DeviceCacheA().callbacks
    assert "a" not in DeviceCacheB().callbacks


def test_post_instantiation_linkage():
    class DeviceCacheA(SharedSingletonDeviceCache):
        instance = None
        callbacks = {}
        aliases = {}

    @DeviceCacheA.link(key="a")
    def foo():
        pass

    assert "a" in DeviceCacheA().callbacks

    @DeviceCacheA.link(key="c")
    def bar():
        pass

    assert "a" in DeviceCacheA().callbacks
    assert "c" in DeviceCacheA().callbacks


def test_callback():
    class DeviceCacheA(SharedSingletonDeviceCache):
        instance = None
        callbacks = {}
        aliases = {}

    @DeviceCacheA.link(key="a")
    def foo():
        return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)

    assert "a" in DeviceCacheA.callbacks
    assert "a" in DeviceCacheA().callbacks

    cache = DeviceCacheA()
    assert hasattr(cache, "data")
    assert cache is DeviceCacheA()
    assert DeviceCacheA() is DeviceCacheA()
    assert cache is DeviceCacheA.instance

    assert "a" not in cache
    assert isinstance(cache["a"], SimNPointLC400)
    assert "a" in cache
    assert "a" in cache.data

    assert "a" in DeviceCacheA.instance.data

    cacheA = DeviceCacheA()
    assert cache is cacheA
    assert "a" in cacheA
    assert "a" in cacheA.data
    assert cache.callbacks is DeviceCacheA.callbacks
    assert cache.callbacks is DeviceCacheA().callbacks
    assert cache.data is DeviceCacheA().data
    assert "a" in DeviceCacheA()
    assert DeviceCacheA()["a"] is foo()


def test_enum_default_cache():
    class DeviceCacheA(SharedSingletonDeviceCache):
        instance = None
        callbacks = {}
        aliases = {}

    class Device(DeviceCacheEnum):
        DEV_A = ("description", "config_id")

        @staticmethod
        def default_cache():
            return DeviceCacheA()

    @Device.DEV_A.link()
    def foo():
        return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)

    assert not Device.DEV_A.cache
    assert Device.DEV_A.instrument
    assert DeviceCacheA()[Device.DEV_A] is foo()
    assert DeviceCacheA()[Device.DEV_A.name] is foo()
    assert foo() is foo()


def test_enum_independent_cache():
    class DeviceCacheA(SharedSingletonDeviceCache):
        instance = None
        callbacks = {}
        aliases = {}

    class DeviceCacheB(SharedSingletonDeviceCache):
        instance = None
        callbacks = {}
        aliases = {}

    class Device(DeviceCacheEnum):
        DEV_A = ("description", "config_id")
        DEV_B = ("description", "config_id", DeviceCacheB)

        @staticmethod
        def default_cache():
            return DeviceCacheA()

    @Device.DEV_A.link()
    def foo():
        return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)

    @Device.DEV_B.link()
    def bar():
        return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)

    assert Device.DEV_A.instrument
    assert DeviceCacheA()[Device.DEV_A] is foo()
    assert DeviceCacheA()[Device.DEV_A.name] is foo()
    assert foo() is foo()

    assert Device.DEV_B.instrument
    assert DeviceCacheB()[Device.DEV_B] is bar()
    assert DeviceCacheB()[Device.DEV_B.name] is bar()
    assert bar() is bar()

    assert bar() is not foo()
    assert DeviceCacheA() is not DeviceCacheB()

    assert Device.DEV_A in DeviceCacheA()
    assert Device.DEV_B in DeviceCacheB()

    assert Device.DEV_A not in DeviceCacheB()
    assert Device.DEV_B not in DeviceCacheA()


# The following needs to be non-local such that the child process has access to the definitions.
# This aspect also complicates its use with a fixture to "reset" any instance state.
class RemoteDeviceCache(SharedSingletonDeviceCache):
    instance = None
    callbacks = {}
    aliases = {}
    address = ("127.0.0.1", 6007)
    timeout = TIMEOUT


SharedMemoryManager.register("RemoteDeviceCache", callable=RemoteDeviceCache, proxytype=RemoteDeviceCache.Proxy, create_method=True)


class RemoteDevice(DeviceCacheEnum):
    DEV_A = ("description", "config_id", RemoteDeviceCache)


class RemoteDeviceB(DeviceCacheEnum):
    DEV_A = ("description", "config_id", RemoteDeviceCache)


class Dev(SimNPointLC400):
    def getpid(self):
        return os.getpid()


@RemoteDevice.DEV_A.link(aliases=("a",))
def foo():
    return Dev(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)


@pytest.fixture(scope="function", autouse=False)
def remote_caching():
    global RemoteDeviceCache
    yield

    # Reset the cache object.
    RemoteDeviceCache.instance = None

    # Since the above cache object was reset, the enum members should no longer ref it.
    for member in RemoteDevice:
        object.__setattr__(member, "cache", None)


def test_thread_mutex():
    def client_func(thread_mutex, proc_mutex):
        assert thread_mutex.acquire(timeout=TIMEOUT*2)
        assert proc_mutex.acquire(timeout=TIMEOUT*2)

    thread_mutex = threading.RLock()
    proc_mutex = multiprocess.RLock()

    client = threading.Thread(target=client_func, args=(thread_mutex, proc_mutex))
    client.start()
    assert not thread_mutex.acquire(timeout=TIMEOUT)
    assert not proc_mutex.acquire(timeout=TIMEOUT)
    client.join()


# def test_proc_mutex():
#     def client_func(thread_mutex, proc_mutex):
#         #assert thread_mutex.acquire(timeout=TIMEOUT*2)
#         assert proc_mutex.acquire(timeout=TIMEOUT*2)
#
#     thread_mutex = threading.RLock()
#     proc_mutex = multiprocess.RLock()
#
#     client = Process(target=client_func, args=(thread_mutex, proc_mutex))
#     client.start()
#     time.sleep(0.5)
#     assert thread_mutex.acquire(timeout=TIMEOUT)
#     assert proc_mutex.acquire(timeout=TIMEOUT)
#     client.join()


def test_device_mutex_over_threads():
    def client_func(device):
        assert device.acquire(timeout=TIMEOUT*2)

    naked_dev = SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)

    client = threading.Thread(target=client_func, args=(naked_dev,))
    client.start()
    with pytest.raises(TimeoutError, match="Failed to acquire lock"):
        naked_dev.acquire(timeout=TIMEOUT)
    client.join()


def test_device_mutex_over_proc():
    def client_func(device):
        assert device.acquire(timeout=TIMEOUT)

    naked_dev = SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)

    client = Process(target=client_func, args=(naked_dev,))
    client.start()
    with pytest.raises(TimeoutError, match="Failed to acquire lock"):
        # threading syncs can't be used between procs - hence the reason for the shared memory managers.
        client.join()


def test_mutex_over_conn():
    with SharedMemoryManager() as manager:
        dic = manager.MutexedDict(timeout=TIMEOUT)
        local_namespace = MutexedNamespace(timeout=TIMEOUT)
        remote_namespace = manager.MutexedNamespace(timeout=TIMEOUT)

        local_namespace.a = 2
        remote_namespace.a = 3

        dic[1] = remote_namespace
        assert dic[1].a == 3

        dic[1] = local_namespace
        with pytest.raises((RemoteError, TimeoutError), match="Failed to acquire lock"):
            assert dic[1].a == 2


def test_device_server(remote_caching):
    with SharedMemoryManager(address=RemoteDeviceCache.address, timeout=TIMEOUT) as manager:
        # Instantiate cache on remote server. Calls to link() need to happen prior to this.
        assert isinstance(RemoteDeviceCache(), BaseProxy)

        # Test remoteness of server and cache and that the cache is on the correct server.
        assert os.getpid() != manager.getpid()
        assert RemoteDeviceCache()._manager.getpid() == manager.getpid()

        # Test singleton - returns same server-side ID for each instantiation.
        cache_id = RemoteDeviceCache()._id
        assert RemoteDeviceCache()._id == cache_id

        # Test that the remote dict aspect of the cache is at least working as expected.
        naked_dev = SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)
        naked_dev.pid = os.getpid()
        RemoteDeviceCache()["a"]# = naked_dev  # Put device on server from client.

        # Test server returns proxy for device.
        assert isinstance(RemoteDeviceCache()["a"], BaseProxy)

        # Test that the same server-side object gets returned.
        a_id = RemoteDeviceCache()["a"]._id
        assert RemoteDeviceCache()["a"]._id == a_id

        # Test del.
        del RemoteDeviceCache()[RemoteDevice.DEV_A]# "a"]
        assert "a" not in RemoteDeviceCache()


def test_auto_load_func_equivalence(remote_caching):
    with SharedMemoryManager(address=RemoteDeviceCache.address, timeout=TIMEOUT) as manager:
        # Test auto load and linked func equivalence.
        assert not isinstance(foo(), BaseProxy)  # Pre cache lookup so just returns (local) linked wrapper.
        assert isinstance(RemoteDeviceCache()[RemoteDevice.DEV_A], BaseProxy)
        assert isinstance(foo(), BaseProxy)  # Post cache lookup so returns (proxy to) linked item cached on the server.
        assert RemoteDeviceCache()[RemoteDevice.DEV_A]._id == foo()._id
        # NOTE: Multiple proxies instances point to same referent.
        assert RemoteDeviceCache()[RemoteDevice.DEV_A] is not foo()


def test_device_cache_namespace_access(remote_caching):
    with SharedMemoryManager(address=RemoteDeviceCache.address, timeout=TIMEOUT) as manager:
        print("####", os.getpid(), manager.getpid())

        cache = RemoteDeviceCache()
        assert isinstance(cache, BaseProxy)
        assert RemoteDeviceCache()._id == cache._id

        device = RemoteDeviceCache()[RemoteDevice.DEV_A]
        assert isinstance(device, BaseProxy)

        assert "get_mutex" in dir(device)
        assert device._method_to_typeid_["get_mutex"] == "MutexProxy"

        mutex = device._callmethod("get_mutex")
        assert isinstance(mutex, BaseProxy)

        assert isinstance(device.get_mutex(), BaseProxy), dir(device)
        assert device.getpid() == manager.getpid()

        # Test proxy namespace attribute access.
        RemoteDeviceCache()[RemoteDevice.DEV_A].new_attr = 44
        # Test that "new_attr" was added to the remote object and not the proxy.
        assert "new_attr" not in RemoteDeviceCache()[RemoteDevice.DEV_A].__dict__
        assert RemoteDeviceCache()[RemoteDevice.DEV_A].new_attr == 44

        assert RemoteDeviceCache()[RemoteDevice.DEV_A].instrument

        # Test device.func() gets called server-side.
        assert RemoteDeviceCache()[RemoteDevice.DEV_A].getpid() == manager.getpid()


def test_from_child_process(remote_caching):
    def child_func(parent_pid):
        assert RemoteDeviceCache()[RemoteDevice.DEV_A].parent_attr == parent_pid
        RemoteDeviceCache()[RemoteDevice.DEV_A].child_attr = os.getpid()

    with SharedMemoryManager(address=RemoteDeviceCache.address, timeout=TIMEOUT):
        RemoteDeviceCache()[RemoteDevice.DEV_A].parent_attr = os.getpid()

        parent_pid = os.getpid()
        child_proc = Process(target=child_func, args=(parent_pid,))
        # Start default addressed SharedMemoryManagerProcess to collect child exceptions from Process.
        with SharedMemoryManager(timeout=TIMEOUT):
            child_proc.start()

            child_pid = child_proc.pid
            assert child_pid != parent_pid

            child_proc.join()

        assert RemoteDevice.DEV_A.child_attr == child_pid


def client_lock_timeout(parent_pid):
    with pytest.raises((RemoteError, TimeoutError)):
        assert RemoteDevice.DEV_A.acquire()

    with pytest.raises((RemoteError, TimeoutError)):
        assert RemoteDevice.DEV_A.parent_attr == parent_pid

    with pytest.raises((RemoteError, TimeoutError)):
        RemoteDevice.DEV_A.child_attr = os.getpid()


def client_lock(parent_pid):
    with RemoteDevice.DEV_A as is_locked:
        assert is_locked

    assert RemoteDevice.DEV_A.parent_attr == parent_pid

    RemoteDevice.DEV_A.child_attr = os.getpid()


def test_enum_api(remote_caching):
    with SharedMemoryManager(address=RemoteDeviceCache.address, timeout=TIMEOUT):

        assert RemoteDevice.DEV_A.instrument

        RemoteDevice.DEV_A.parent_attr = os.getpid()
        assert RemoteDeviceCache()[RemoteDevice.DEV_A].parent_attr == os.getpid()
        assert RemoteDevice.DEV_A.parent_attr == os.getpid()
        assert foo().parent_attr == os.getpid()

        # Test locks.
        try:
            outer_lock = None
            outer_lock = RemoteDevice.DEV_A.acquire()
            assert outer_lock
            with RemoteDevice.DEV_A as inner_lock:
                assert inner_lock
                try:
                    inner_most_lock = None
                    inner_most_lock = RemoteDevice.DEV_A.acquire()
                    assert inner_most_lock
                finally:
                    if inner_most_lock:
                        RemoteDevice.DEV_A.release()
        finally:
            if outer_lock:
                RemoteDevice.DEV_A.release()


def test_enum_api_from_child_process(remote_caching):
    with SharedMemoryManager(address=RemoteDeviceCache.address, timeout=TIMEOUT):

        RemoteDevice.DEV_A.parent_attr = os.getpid()

        client = Process(target=client_lock_timeout, args=(os.getpid(),))
        with RemoteDevice.DEV_A as is_locked:
            assert is_locked
            client.start()
            client.join()

        client = Process(target=client_lock, args=(os.getpid(),))
        client.start()
        client_pid = client.pid
        client.join()
        assert RemoteDevice.DEV_A.child_attr == client_pid

        client = Process(target=client_lock_timeout, args=(os.getpid(),))
        try:
            outer_lock = None
            outer_lock = RemoteDevice.DEV_A.acquire(timeout=TIMEOUT)
            assert outer_lock
            client.start()
            client.join()
        finally:
            if outer_lock:
                RemoteDevice.DEV_A.release()

        client = Process(target=client_lock, args=(os.getpid(),))
        client.start()
        client_pid = client.pid
        client.join()
        assert RemoteDevice.DEV_A.child_attr == client_pid


def test_enum_mutual_cache(remote_caching):
    with SharedMemoryManager(address=RemoteDeviceCache.address, timeout=TIMEOUT):
        RemoteDevice.DEV_A.attr1 = 1234567
        assert RemoteDeviceB.DEV_A.attr1 == 1234567


def test_enum_equivalence(remote_caching):
    assert RemoteDevice(RemoteDeviceB.DEV_A) is RemoteDevice.DEV_A
    assert RemoteDeviceB(RemoteDevice.DEV_A) is RemoteDeviceB.DEV_A


class RemoteDeviceC(DeviceCacheEnum):
    DEV_B = ("B", "config_id_B", RemoteDeviceCache)
    DEV_C = ("C", "config_id_C", RemoteDeviceCache)
    DEV_D = ("D", "config_id_D", RemoteDeviceCache)


@pytest.fixture(scope="function", autouse=False)
def remote_cachingC():
    global RemoteDeviceCache
    yield

    # Reset the cache object.
    RemoteDeviceCache.instance = None

    # Since the above cache object was reset, the enum members should no longer ref it.
    for member in RemoteDeviceC:
        object.__setattr__(member, "cache", None)


@RemoteDeviceC.DEV_B.link()
def fooA():
    return Dev(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)


@RemoteDeviceC.DEV_C.link()
def fooB():
    return Dev(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)


@RemoteDeviceC.DEV_D.link()
def fooC():
    return Dev(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)


def test_keys(remote_cachingC):
    with SharedMemoryManager(address=RemoteDeviceCache.address, timeout=TIMEOUT):
        RemoteDeviceC.open_all()
        assert RemoteDeviceCache().keys() == [member.name for member in RemoteDeviceC]


def test_values(remote_cachingC):
    with SharedMemoryManager(address=RemoteDeviceCache.address, timeout=TIMEOUT):
        RemoteDeviceCache().open_all()
        for value in RemoteDeviceCache().values():
            assert isinstance(value, BaseProxy)


def test_items(remote_cachingC):
    with SharedMemoryManager(address=RemoteDeviceCache.address, timeout=TIMEOUT):
        RemoteDeviceCache().open_all()
        items = RemoteDeviceCache().items()
        for key, value in items:
            assert isinstance(value, BaseProxy)
            assert RemoteDeviceCache()[key]._id == value._id


def test_pop(remote_cachingC):
    with SharedMemoryManager(address=RemoteDeviceCache.address, timeout=TIMEOUT):
        RemoteDeviceCache().open_all()
        length = len(RemoteDeviceCache())
        assert isinstance(RemoteDeviceCache().pop(RemoteDeviceC.DEV_C), BaseProxy)
        assert len(RemoteDeviceCache()) == length - 1
        assert RemoteDeviceC.DEV_C not in RemoteDeviceCache()
        assert RemoteDeviceC.DEV_B in RemoteDeviceCache()
        assert RemoteDeviceC.DEV_D in RemoteDeviceCache()
