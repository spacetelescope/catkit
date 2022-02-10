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
