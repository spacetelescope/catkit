# Concurrency


### Terminology & Concepts

 -  **Critical section:** A section of code that needs mutually exclusive access. (https://en.wikipedia.org/wiki/Critical_section)
 - **Mutex:** Abstract term for which locks are an implementation of obtaining **MUT**ual **EX**clusion of a given critical section (crit-sec).
   - https://en.wikipedia.org/wiki/Mutual_exclusion
   - https://en.wikipedia.org/wiki/Lock_(computer_science)
 - **Race condition:** https://en.wikipedia.org/wiki/Race_condition (See "In software" section).
 - **Deadlock:** https://en.wikipedia.org/wiki/Deadlock


### Python Threading Types

https://docs.python.org/3/library/threading.html

 - **Lock:** https://docs.python.org/3/library/threading.html#lock-objects (non-reentrant lock)
 - **RLock:** https://docs.python.org/3/library/threading.html#rlock-objects (reentrant lock)
  (Note: All catkit devices are mutexed using a reentrant lock and not a non-reentrant lock.)
 - **Barrier:** https://docs.python.org/3/library/threading.html#barrier-objects
 - **Event:** https://docs.python.org/3/library/threading.html#event-objects


### Python Multiprocessing

NOTE: All Python multiprocessing objects, e.g., ``multiprocessing.Event``, are, under the hood, just their threading
counterparts, e.g., ``threading.Event``.

https://docs.python.org/3/library/multiprocessing.html

 - **Shared memory managers:** https://docs.python.org/3/library/multiprocessing.html#managers
 - **Default available types:** https://docs.python.org/3/library/multiprocessing.html#multiprocessing.managers.SyncManager
 - **Proxy objects:** https://docs.python.org/3/library/multiprocessing.html#proxy-objects


### Catkit Multiprocessing

https://github.com/spacetelescope/catkit/blob/develop/catkit/multiprocessing.py

Whilst it's possible to use Python's standard multiprocessing types, catkit's derived types should be used instead.

 - **catkit.multiprocessing.Process:** Connects to exception manager and implicitly shares exceptions between child and
   parent processes. NOTE: The exception manager must be started for this functionality to work. The "exception manager"
   uses catkit's default server address, and as such
   ```python
   my_proc = catkit.multiprocessing.Process(...)
   with catkit.multiprocessing.SharedMemoryManager():
       my_proc.start()
       my_proc.join()
   ```
 - **catkit.multiprocessing.Mutex:** A container for a ``threading.RLock``, with proxy. Main difference is that
   ``acquire()`` has a default timeout.
 - **catkit.multiprocessing.SharedMemoryManager:** Derived from multiprocessing.SyncManager. Adds functionality to cache
   and share some synchronization types, i.e., events and barriers, via, e.g, ``get_event()`` & ``get_barrier()``.
 - **catkit.testbed.caching.MutexedDict:** Mutexed shared dictionary.


#  Concurrent Testbed Usage. (WIP)

This README documents ``catkit.multiprocessing``, ``catkit.testbed.caching``, and ``catkit.testbed.experiment`` and
their usage in developing concurrent experiments with shared access to testbed hardware.

## Overview

Instead of running a single sequential experiment and/or control loop on your testbed you can now run multiple
concurrent experiments and control/loops on separate Python processes whilst still sharing all testbed hardware across
said processes.

Since pretty much all Python interpreters (e.g., CPython) don't yet support real threading (blame the GIL) this has to
be achieved using multiprocessing by running multiple Python interpreter sessions on their own processes.
Inter process communication is brokered using Python's shared memory managers available in``multiprocessing.managers``.

The shared memory manager model works by starting shared memory servers (run on dedicated processes) in which Python
objects can be instantiated upon and shared to multiple client processes via proxies. Such proxies then act in
pretty much the same was as their referent instances would.
See https://docs.python.org/3/library/multiprocessing.html#managers.

The above mentioned ``catkit.multiprocessing`` module builds upon this framework extending its functionality.
The principle addition addresses the frameworks most lacking drawback which is that shared proxies have to be just that,
shared. With the original framework, this is achieved only by passing the proxies as ``args`` to
``multiprocessing.Process`` when concurrent client processes are instantiated.  This requires all proxies to exist
up-front and before any and all processes are started, thus completely limiting any dynamic object creation.

In addition to this, the original framework doesn't guarantee atomic access to shared objects (only object creation is
guaranteed to be atomic). Catkit provides some base proxies that mutex both attribute access and method calls. Such
mutexes are also exposed to the client such that multiple accesses can be mutexed thus allowing for arbitrarily wider
critical sections. This functionality is essential for inter-dependent hardware control operations where the state of
the testbed needs to be guaranteed not to have been altered by a concurrent process.


## Core classes:

* ``catkit.multiprocessing.Process``: Dumps child process exceptions on a dedicated shared memory server such that they
  can be accessed/caught by the parent (upon join).
* ``catkit.multiprocessing.SharedMemoryManager``: Shared memory manager.
* ``catkit.multiprocessing.MutexedNamespaceSingleton``: Base type for any shared object.
* ``catkit.multiprocessing.MutexedNamespaceAutoProxy``: Proxy type for any shared object.
* ``catit.testbed.caching.SharedSingletonDeviceCache``: Shared device cache.
* ``catkit.testbed.caching.DeviceCacheEnum``: Enum API type for shared device cache.
* ``catkit.testbed.experiment.SafetyTest``: Base type for all safety tests.
* ``catkit.testbed.experiment.Testbed``: Base type for encapsulating the entire testbed infrastructure, e.g.,
  managing and monitoring safety tests, starting and owning all shared memory servers etc.
* ``catkit.testbed.experiment.Experiment``: Base type encapsulating the experiment flow or control loop.

#### Hardware access full stack flow:

The principle design feature is to remove awareness of much of the underlying infrastructure from the end user, thus
granting them a simpler and neater task when implementing experiments and control algorithms. Such lower-level infrastructure
includes the core infrastructure of managing device connections and lifetimes, managing shared access, safety tests, and
most inter process communication, e.g., child exception handling etc. The only real exception to this is their need to
understand and implement adequate critical sections where needed as per the given experiment or control loop.

This abstraction is layered as the following (top down):

``enum API`` -> ``device cache (proxy)`` -> ``device cache stored on separate server process``

* Enum member attribute access: ``Device.Camera.TakeImage()`` - Device:=Enum, Camera:=member, TakeImage:=attribute. This
  is the only layer that the user interfaces with.
* Lookup device proxy in client side proxy cache and return if present.
* Upon cache miss lookup device in underlying device cache proxy (hosted on shared server). Device caches exits per enum
  member, if that member's cache hasn't yet been "activated" connect to server and instantiate the device from the
  client.
* Upon miss in the device cache, instantiate device, open connection, populate underlying device cache, return proxy to
  client, populate client side proxy cache with proxy, return proxy to caller.
* Unwind back up the call stack.
* Access attribute via device proxy.
* Execute ``TakeImage`` on the remote server returning any resultant data back to client.

Device connections and lifetimes are managed hierarchically as the following (bottom up):
* Device objects are managed by their respective cache. E.g., the cache opens and closes connections.
* Device caches are managed by their shared memory manager/servers.
* The device servers are managed by ``catkit.testbed.experiment.Testbed``.

## Implementation Details

Not needing to pass proxies to ``Process`` up front can be resolved by at least two patterns:
* Adding methods to the servers for accessing shared dicts of objects.
* Instantiating singletons on the servers.

Catkit adopts both of these patterns. For example, synchronization primitives, such as mutexes and barriers, are cached
in dicts on a given server and can be looked up by name.  All other objects, such as the
device/instrument objects, use the singleton pattern., one major design flaw with the above base model is that the

Lastly, the original framework requires all proxies to be created prior to starting the server and within the same
parent process.
