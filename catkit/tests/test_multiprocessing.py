import os
from threading import BrokenBarrierError
import time

from multiprocess.context import TimeoutError
from multiprocess.managers import State
import pytest

from catkit.multiprocessing import Process, SharedMemoryManager

TIMEOUT = 10  # Use a shorter timeout for testing.


def test_child_exception():
    def client_func():
        raise RuntimeError("123456789")

    with SharedMemoryManager() as manager:
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


def client_barrier(sleep, parties, l, name_mangle=False):
    manager = SharedMemoryManager()
    manager.connect()
    name = f"test_barrier_{sleep}" if name_mangle else "test_barrier"
    barrier = manager.get_barrier(name, parties)
    t0 = time.time()
    time.sleep(sleep)
    barrier.wait(timeout=TIMEOUT)  # NOTE: The barrier release order is not guaranteed.
    l.append(int(time.time() - t0))


def test_single_barrier():
    with SharedMemoryManager() as manager:
        l = manager.list()

        clients = [Process(target=client_barrier, args=(6, 3, l)),
                   Process(target=client_barrier, args=(0, 3, l)),
                   Process(target=client_barrier, args=(0, 3, l))]

        for client in clients:
            client.start()

        for client in clients:
            client.join()

        # We Expect to see that the timer wrapping the sleep and the barrier for each client to be that of the longest.
        assert l._getvalue() == [6, 6, 6], l._getvalue()


def test_multiple_barriers():
    with SharedMemoryManager() as manager:
        l = manager.list()

        clients = [Process(target=client_barrier, args=(6, 1, l, True)),
                   Process(target=client_barrier, args=(0, 1, l, True)),
                   Process(target=client_barrier, args=(0, 1, l, True))]

        for client in clients:
            client.start()

        for client in clients:
            client.join()

        # We Expect to see that the timer wrapping the sleep and the barrier for each client to be that of their sleep.
        assert l._getvalue() == [0, 0, 6], l._getvalue()


def test_broken_barrier():
    with SharedMemoryManager() as manager:
        l = manager.list()

        # More parties than process will cause barrier.wait() to timeout.
        client = Process(target=client_barrier, args=(6, 3, l))
        client.start()
        with pytest.raises(BrokenBarrierError):
            client.join()
