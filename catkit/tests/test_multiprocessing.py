import copy
import os
import sys
from threading import BrokenBarrierError
import time


from multiprocess.context import AuthenticationError, TimeoutError
from multiprocess.managers import BaseProxy, NamespaceProxy, State
import numpy as np
import pytest

from catkit.emulators.npoint_tiptilt import SimNPointLC400
from catkit.interfaces.Instrument import Instrument, InstrumentBaseProxy
from catkit.multiprocessing import Mutex, Process, SharedMemoryManager

CI = os.environ.get('CI') in ('True', 'true')

TIMEOUT = 5  # Use a shorter timeout for testing.


def test_child_exception():
    def client_func():
        raise RuntimeError("123456789")

    client = Process(target=client_func)
    client.start()
    with pytest.raises(RuntimeError, match="123456789"):
        client.join()


def test_pid():
    def client_func(pid):
        manager = SharedMemoryManager()
        manager.connect()
        server_pid = manager.getpid()

        client_pid = os.getpid()
        assert server_pid != client_pid, f"Server ({server_pid}) shouldn't be running on client ({client_pid})"
        assert server_pid == pid, f"Server ({server_pid}) connected to from client ({client_pid}) should be same as that started by manager ({pid})"

    with SharedMemoryManager() as manager:
        parent_pid = os.getpid()
        server_pid = manager.getpid()

        assert server_pid != parent_pid

        n_clients = 2
        clients = [Process(target=client_func, args=(server_pid,)) for x in range(n_clients)]

        for client in clients:
            client.start()

        for client in clients:
            client.join()


def test_authentication():
    authkey = os.urandom(128)

    def client_func():
        manager = SharedMemoryManager(authkey=authkey)
        manager.connect()

    client = Process(target=client_func)

    with SharedMemoryManager(authkey=authkey):
        client.start()
        client.join()


def test_authentication_from_address():
    address = ("127.0.0.1", 7777, os.urandom(128))

    def client_func():
        manager = SharedMemoryManager(address=address)
        manager.connect()

    client = Process(target=client_func)

    with SharedMemoryManager(address=address):
        client.start()
        client.join()


def test_failed_authentication():
    def client_func():
        manager = SharedMemoryManager(authkey=os.urandom(128))
        with pytest.raises(AuthenticationError):
            manager.connect()

    client = Process(target=client_func)

    with SharedMemoryManager(authkey=os.urandom(128)):
        client.start()
        client.join()


def test_no_persistent_server():
    manager = SharedMemoryManager()
    with pytest.raises(ConnectionRefusedError):
        manager.connect()


def test_locks():
    def client_func2():
        manager = SharedMemoryManager()
        manager.connect()
        with pytest.raises(TimeoutError):
            with manager.get_lock("test_lock"):  # This will timeout as the parent process has already acquired this.
                pass

    client = Process(target=client_func2)

    with SharedMemoryManager() as manager:
        assert manager._state.value == State.STARTED  # Oddly manager._state is State.Started doesn't work.
        with manager.get_lock("test_lock", timeout=TIMEOUT) as is_locked:
            assert is_locked
            client.start()
            client.join()


def test_RLock_is_renterant_per_connection_and_process():

    # BaseProxy caches connections per server address, so multiple proxies will use the exact same connection object.
    # Since these are cached as a class attribute, a separate cache exits per process (otherwise non of this would even be needed).
    # The server is started on a separate process which it then spins up a thread to accept connections which that in turn
    # spins up a new thread per connection from a client. The server has a thread per client connection.
    # Shared reentrant locks are just threading.RLock instances that exist on the server process but on a specific
    # client thread - for which these locks are reentrant only to a single given thread.
    # Since their proxy calls `acquire()` and `release()` on the server (not the client) it would need to
    # be threaded such that it is reentrant per process and thus not invalidating the lock entirely.

    with SharedMemoryManager() as manager:
        lock1 = manager.get_lock("my_lock")
        lock1.acquire(timeout=TIMEOUT)

        # New connection.
        manager2 = SharedMemoryManager(own=False)
        manager2.connect()

        assert manager is not manager2
        assert manager._Listener is manager2._Listener

        lock2 = manager2.get_lock("my_lock")
        lock2.acquire(timeout=TIMEOUT)


def test_mutex_equivalence():
    a = Mutex()
    b = Mutex()

    assert a is not b
    assert a != b

    c = Mutex(lock=a)
    assert c is not a
    assert c == a

    d = Mutex(lock=a.get_mutex())
    assert d is not a
    assert d == a


def test_mutex_equivalence_by_proxy():
    with SharedMemoryManager() as manager:
        a = manager.Mutex()
        assert isinstance(a, Mutex.Proxy)
        b = manager.Mutex()

        assert a is not b
        assert a != b

        c = copy.copy(a)
        assert isinstance(c, Mutex.Proxy)

        assert c is not a
        assert a.get_mutex_id() == c.get_mutex_id()
        assert a.__eq__(c)
        assert c == a
        assert a == c

        d = manager.Mutex(lock=a)
        assert d == a


def client_barrier(parties, flag):
    manager = SharedMemoryManager()
    manager.connect()
    assert flag.get() == 2
    barrier1 = manager.get_barrier("initial flag", parties)
    barrier1.wait()
    barrier2 = manager.get_barrier("flag set", parties)
    barrier2.wait()
    assert flag.get() == 3


def test_single_barrier():
    with SharedMemoryManager() as manager:
        flag = manager.Value(int, 2)

        parties = 4
        barrier1 = manager.get_barrier("initial flag", parties, timeout=TIMEOUT)

        barrier2 = manager.get_barrier("flag set", parties, timeout=TIMEOUT)

        clients = [Process(target=client_barrier, args=(parties, flag)),
                   Process(target=client_barrier, args=(parties, flag)),
                   Process(target=client_barrier, args=(parties, flag))]
        assert len(clients) == parties - 1

        for client in clients:
            client.start()

        barrier1.wait()  # The reason events exits...
        flag.set(3)
        barrier2.wait()  # NOTE: The barrier release order is not guaranteed.

        for client in clients:
            client.join()


def test_broken_barrier():
    with SharedMemoryManager() as manager:
        flag = manager.Value(int, 2)

        # More parties than processes/threads will cause barrier.wait() to timeout.
        client = Process(target=client_barrier, args=(2, flag))
        client.start()
        with pytest.raises(BrokenBarrierError):
            client.join()


def multiple_client_connections():
    manager = SharedMemoryManager()
    manager.connect()
    pid = manager.getpid()

    manager2 = SharedMemoryManager()
    manager2.connect()
    pid2 = manager2.getpid()
    assert pid == pid2

    # Check that the 1st manager's connection still works.
    assert pid == manager.getpid()
    assert manager.getpid() == manager2.getpid()


def test_multiple_client_connections_from_same_proc():
    with SharedMemoryManager() as manager:
        client = Process(target=multiple_client_connections)
        client.start()
        client.join()


def concurrent_client_connections(parties):
    manager = SharedMemoryManager()
    manager.connect()

    barrier = manager.get_barrier("this barrier", parties)
    barrier.wait()
    time.sleep(1)
    barrier.wait()


def test_multiple_client_connections_from_concurrent_procs():
    with SharedMemoryManager() as manager:
        n_clients = 10
        clients = [Process(target=concurrent_client_connections, args=(n_clients,)) for x in range(n_clients)]

        for client in clients:
            client.start()

        for client in clients:
            client.join()


def test_conn_from_same_as_start():
    with SharedMemoryManager() as manager:
        manager.connect()


def test_is_server_process():

    def assert_is_server_process(server_pid):
        assert os.getpid() == server_pid
        assert SharedMemoryManager.is_a_server_process

    SharedMemoryManager.register("assert_is_server_process", callable=assert_is_server_process)

    assert not SharedMemoryManager.is_a_server_process

    with SharedMemoryManager() as manager:
        assert not SharedMemoryManager.is_a_server_process
        server_pid = manager.getpid()
        assert os.getpid != server_pid
        manager.assert_is_server_process(server_pid)


def test_AutoProxy_build_cache():
    pass


def test_a():
    import catkit.multiprocessing

    def run():
        import catkit.multiprocessing
        assert SharedMemoryManager.is_a_server_process != "ljbi"
        assert SharedMemoryManager.is_a_server_process is False
        assert catkit.multiprocessing.DEFAULT_TIMEOUT != 100
        assert catkit.multiprocessing.DEFAULT_TIMEOUT == 60

    SharedMemoryManager.is_a_server_process = "ljbi"

    catkit.multiprocessing.DEFAULT_TIMEOUT = 100

    cli = Process(target=run)
    cli.start()
    cli.join()


class Foo:
    @property
    def position(self):
        return "this is a property"


SharedMemoryManager.register("Foo", callable=Foo, proxytype=NamespaceProxy, create_method=True)


def test_remote_property():
    with SharedMemoryManager() as manager:
        obj = manager.Foo()
        assert isinstance(obj, BaseProxy)
        assert obj.position == "this is a property"


class InstrumentWithProperty(SimNPointLC400):
    @property
    def position(self):
        return "this is a property"


SharedMemoryManager.register("InstrumentWithProperty", callable=InstrumentWithProperty, proxytype=InstrumentWithProperty.Proxy, create_method=True)


def test_instrument_property():
    with SharedMemoryManager() as manager:
        obj = manager.InstrumentWithProperty(config_id="npoint_tiptilt_lc_400", com_id="dummy", timeout=TIMEOUT)
        assert isinstance(obj, BaseProxy)
        assert obj.position == "this is a property"


class DummyInst(Instrument):
    instrument_lib = None

    def initialize(self, *args, **kwargs):
        self.data = None

    def _open(self):
        return self

    def _close(self):
        pass

    def set_data(self, data, n_bytes, do_copy):
        self.data = copy.deepcopy(data) if do_copy else data
        assert sys.getsizeof(self.data) == n_bytes

    def get_data(self):
        return self.data

    class WaferThinProxy(InstrumentBaseProxy):
        _method_to_typeid_ = {"__enter__": "FastDummyInstProxy", **InstrumentBaseProxy._method_to_typeid_}

        def set_data(self, *args, **kwargs):
            return self._callmethod("set_data", args=args, kwds=kwargs)

        def get_data(self, *args, **kwargs):
            return self._callmethod("get_data", args=args, kwds=kwargs)


SharedMemoryManager.register("DummyInst", callable=DummyInst, proxytype=DummyInst.Proxy, create_method=True)
SharedMemoryManager.register("FastDummyInst", callable=DummyInst, proxytype=DummyInst.WaferThinProxy, create_method=True)
SharedMemoryManager.register("FastDummyInstProxy", proxytype=DummyInst.WaferThinProxy, create_method=False)


# shape, limit = (712, 712), 50  # Image.
# shape, limit = ((34, 34, 2)), 900  # Double Boston Dm command.
@pytest.mark.skipif(CI, reason="Perf tests")
@pytest.mark.parametrize(("shape", "limit"), (((712, 712), 50), ((34, 34, 2), 900)))
def test_Mbps(shape, limit):
    with SharedMemoryManager(address=("127.0.0.1", 6060)) as manager:
        n = 100
        dtype = np.float64
        data = np.zeros(shape, dtype=dtype)
        n_B = sys.getsizeof(data)
        n_Mb = n_B*8/1e6

        t_set = [0]*n
        t_get = [0]*n

        device = manager.DummyInst("dummy")
        # device = manager.FastDummyInst("dummy")

        with device as dev:
            with dev.get_mutex():
                for i in range(n):
                    t0 = time.perf_counter_ns()
                    dev.set_data(data, n_B, True)
                    t1 = time.perf_counter_ns()
                    t_set[i] = (t1 - t0)*1e-9

                    t0 = time.perf_counter_ns()
                    _resp = dev.get_data()
                    t1 = time.perf_counter_ns()
                    t_get[i] = (t1 - t0)*1e-9

                    print(f"{i}: {n_Mb/t_set[i]:.2f}Mbps {n_Mb/t_get[i]:.2f}Mbps")

        mean_get_mbps = n_Mb/np.mean(t_get)
        mean_set_mbps = n_Mb/np.mean(t_set)
        mean_rate = 1/np.mean(t_get)

        print(f"Mean perf: GET: {mean_get_mbps:.2f}Mbps, SET: {mean_set_mbps:.2f}Mbps")
        print(f"Mean rate for image transfer of {shape} ({dtype}): {mean_rate:.2f}Hz")
        assert mean_rate > limit
        # assert False
