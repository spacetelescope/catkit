from abc import abstractmethod, ABC
from collections import namedtuple, UserDict
from enum import Enum
from multiprocess.managers import AcquirerProxy, DictProxy
import warnings

from catkit.interfaces.Instrument import Instrument
from catkit.multiprocessing import DEFAULT_SHARED_MEMORY_SERVER_ADDRESS, DEFAULT_TIMEOUT, Mutex, SharedMemoryManager


class UserCache(UserDict, ABC):
    @abstractmethod
    def load(self, key, *args, **kwargs):
        """ Func to load non-existent cache entries. """

    def __getitem__(self, key):
        item = self.data.get(key, None)
        if item is None:
            self.load(key)
            return self.data[key]
        else:
            return item

    class Proxy(DictProxy):
        pass


class ContextCache(UserCache):
    """ Cache of context managed items (non device/instrument). """
    def load(self, key, *args, **kwargs):
        pass

    def __delitem__(self, key):
        if getattr(self.data[key], "__exit__", None):
            try:
                self.data[key].__exit__(None, None, None)
            except Exception:
                warnings.warn(f"{key} failed to exit.")
        del self.data[key]

    def __del__(self):
        self.clear()


class MutexedCache(Mutex, UserCache):
    """ The use of locks isn't necessary to mutex access to `self.data`, that is handled by the manager.
        However, it is necessary if wanting to mutex multiple accesses from the caller.
    """

    def load(self, key, *args, **kwargs):
        """ Func to load non-existent cache entries. """
        # This is abstract for the base class but we'll make it concrete here. It ca be overridden if desired.
        raise KeyError(key)

    def __getitem__(self, item):
        with self:
            return super().__getitem__(item)

    def __setitem__(self, key, value):
        with self:
            super().__setitem__(key, value)

    def __delitem__(self, key):
        with self:
            super().__delitem__(key)

    class Proxy(AcquirerProxy, DictProxy):
        _exposed_ = ('__contains__', '__delitem__', '__getitem__', '__iter__', '__len__', '__setitem__', 'clear',
                     'copy', 'get', 'has_key', 'items', 'keys', 'pop', 'popitem', 'setdefault', 'update', 'values',
                     'acquire', 'release')
        pass


SharedMemoryManager.register("MutexedCache", callable=MutexedCache, proxytype=MutexedCache.Proxy)


# This will get nuked once all hardware adheres to the Instrument interface.
def set_keep_alive(device, value):
    if isinstance(device, Instrument):
        device._Instrument__keep_alive = value
    else:
        device._keep_alive = value


class DeviceCache(UserCache):

    Callback = namedtuple("callback", ["func", "root_key", "aliases"])

    class OwnedContext:
        """ Container to "own" cache entries such that they can't be closed by external with stmnts. """

        # NOTE: A trivial container will not suffice since it will cause isinstance() checks on OwnedContext objects
        # returned from DeviceCache to fail. Dynamic inheritance and ugly __getattribute__() switching is required.

        def __new__(cls, device, *args, **kwargs):
            class ChildOwnedContext(cls, device.__class__):
                pass
            return super().__new__(ChildOwnedContext, *args, **kwargs)

        def __del__(self):
            super().__getattribute__("un_own")()

        def __init__(self, device):
            object.__setattr__(self, "_owned_obj", device)
            # Open.
            super().__getattribute__("_owned_obj").__enter__()

        def __getattribute__(self, item):
            if item in ("__del__", "__init__", "__enter__", "__exit__", "_owned_obj", "un_own"):
                return super().__getattribute__(item)
            else:
                return super().__getattribute__("_owned_obj").__getattribute__(item)

        def __setattr__(self, name, value):
            return super().__setattr__(object.__getattribute__("_owned_obj"), name, value)

        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception_value, exception_traceback):
            pass

        def un_own(self):
            obj = super().__getattribute__("_owned_obj")
            if obj is None or obj.instrument is None:
                return
            set_keep_alive(obj, False)
            # Close.
            try:
                obj.__exit__(None, None, None)
            except Exception:
                # Don't raise so that other devices can exit.
                warnings.warn(f"{obj.config_id} failed to close correctly.")
            finally:
                pass
                # object.__setattr__(self, "__owned_obj", None)
            return obj

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aliases = {}
        self.callbacks = {}

    def __enter__(self):
        self.clear()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.clear()

    def __del__(self):
        self.clear()

    def __delitem__(self, key):
        self.data[key].un_own()
        del self.data[key]

    def __getitem__(self, item):
        try:
            return self.data[item]
        except KeyError:
            # Try aliases.
            ret = self.aliases.get(item)
            # If that fails, auto load.
            if ret is None:
                self.load(item)
                # `item` may have been an alias, in which case self.data[item] won't suffice as self.data contains only
                # root_keys (to simplify closures). In which case, aliases need to be checked and the simplest way to do
                # this is to call __getitem__() (again).
                # Infinite recursion shouldn't occur as load() should correctly populate self.data[item].
                return self.__getitem__(item)
            else:
                return ret

    def __setitem__(self, key, value):
        def raise_on_collision(obj_a, obj_b):
            nonlocal key
            # Raise on collision but only if they're NOT the same underlying object.
            obj_a = obj_a._owned_obj if isinstance(obj_a, self.OwnedContext) else obj_a
            obj_b = obj_b._owned_obj if isinstance(obj_b, self.OwnedContext) else obj_b

            if obj_a is not obj_b:
                raise KeyError(f"Cache collision: '{key}' key already exists in device cache.")

        if key in self.data:
            raise_on_collision(self.data[key], value)
        elif key in self.aliases:
            raise_on_collision(self.aliases[key], value)
        else:
            self.data[key] = self.OwnedContext(value)

    def open_all(self):
        if not self.callbacks:
            return

        for callback in self.callbacks.values():
            self.__getitem__(callback.root_key)
        return self

    def load(self, key, *args, **kwargs):
        callback = self.callbacks.get(key)
        if callback is None:
            raise KeyError(f"The cache key '{key}' was either never decorated with link() or adequate aliases weren't provided.")

        # It's possible that the key passed is an alias rather than the root key, so map back to key_root.
        # This ensures that orphaned aliases don't exits without root_keys in self.data.
        key = callback.root_key
        callback = self.callbacks.get(key)

        # Instantiate, open, and own it.
        self.update({key: callback.func()})
        # Register aliases.
        aliases = callback.aliases
        if aliases:
            for alias in aliases:
                # Check for collisions.
                if alias in self.aliases:
                    raise KeyError(f"Cache collision: '{alias}' key already exists in device cache.")
                self.aliases[alias] = self.data[key]

    def link(self, key, aliases=None):
        """ Decorator for testbed device funcs to automatically cache them. """
        def decorator(func):
            def wrapper(*args, **kwargs):
                # Return cached instances if present.
                try:
                    return self.data[key]  # Only possible if a previous cache access occurred.
                except (KeyError, NameError):  # Do this to help experiment.RestrictedDeviceCache when locked.
                    pass
                # Call func.
                ret = func(*args, **kwargs)
                # Don't automatically cache, if the user wants it cached they need to access via the cache itself.
                #self.update({key: ret})
                return ret
            # Register callback to be called upon a cache miss. Register func and not wrapper to avoid future pretzeling.
            self.callbacks[key] = self.Callback(func=func, root_key=key, aliases=aliases)
            if aliases:
                for alias in aliases:
                    # Check for collisions.
                    if alias in self.callbacks:
                        raise KeyError(f"Cache collision: '{alias}' key already exists in device cache.")
                    self.callbacks[alias] = self.Callback(func=func, root_key=key, aliases=None)
            return wrapper
        return decorator

    def copy(self, *args, **kwargs):
        raise NotImplementedError("Don't copy!")

    def clear(self):
        self.aliases.clear()
        #self.callbacks.clear()  # Don't clear this, it's populated at import time.
        return super().clear()


class DeviceCacheEnum(Enum):
    """ Enum API to DeviceCache. """

    def __init__(self, description, config_id):
        self.description = description
        self.config_id = config_id
        self.__object_exists = True

    @classmethod
    def _missing_(cls, value):
        """ Allow lookup by config_id, such that DeviceCacheEnum(config_id) returns its matching member. """
        for item in cls:
            if value in (item.config_id, item.description):
                return item

    def __getattr__(self, item):
        global devices
        """ Allow DeviceCacheEnum.member.attribute -> catkit.testbed.devices[member].attribute """
        config_id = object.__getattribute__(self, "config_id")
        member = self.__class__(config_id)
        device = devices[member]
        return device.__getattribute__(item)

    def __setattr__(self, name, value):
        if "_DeviceCacheEnum__object_exists" in self.__dict__:
            config_id = object.__getattribute__(self, "config_id")
            member = self.__class__(config_id)
            device = devices[member]
            device.__setattr__(name, value)
        else:
            object.__setattr__(self, name, value)


class ImmutableDeviceCacheEnum(DeviceCacheEnum):
    def __setattr__(self, name, value):
        if "_DeviceCacheEnum__object_exists" in self.__dict__:
            raise AttributeError("Attribute assignment prohibited.")
        object.__setattr__(self, name, value)


class RestrictedDeviceCache(DeviceCache):
    """ Restricted version of catkit.testbed.caching.DeviceCache that allows linking but nothing else until unlocked. """

    def __init__(self, *args, **kwargs):
        super().__setattr__("__lock", False)  # Unlock such that super().__init__() has access.
        super().__init__(*args, **kwargs)
        super().__setattr__("__lock", True)
        super().__setattr__("__unrestricted", ("aliases", "Callback", "callbacks", "link"))

    def __getattribute__(self, item):
        if (super().__getattribute__("__lock") and
                item not in super().__getattribute__("__unrestricted")):
            raise NameError(f"Access to '{item}' is restricted The device cache can only be used from a running experiment.")
        return super().__getattribute__(item)

    def __setattr__(self, item, value):
        if (super().__getattribute__("__lock") and
                item not in super().__getattribute__("__unrestricted")):
            raise NameError(f"Access to '{item}' is restricted! The device cache can only be used from a running experiment.")
        return super().__setattr__(item, value)

    def __enter__(self):
        super().__setattr__("__lock", False)
        return super().__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)
        super().__setattr__("__lock", True)

    def __del__(self):
        super().__setattr__("__lock", False)
        self.clear()


class SharedState:
    """ Container for SharedMemoryManager and (default) SharedMemoryManager().SharedState().

    Parameters
    ----------
    address : tuple
        A tuple of the following `(IP, port)` to start the shared server on.
    timeout : float, int
        Default timeout for mutexing access.
    own : bool
        True: Use from parent to "own" and thus start the server. Will also shutdown when deleted.
        False: (default) Use from clients to connect to an already started server.
    """

    def __init__(self, *args, address=DEFAULT_SHARED_MEMORY_SERVER_ADDRESS,
                 timeout=DEFAULT_TIMEOUT,
                 own=False,
                 namespace="SharedState",
                 **kwargs):
        super().__init__(*args, **kwargs)
        self._own = own  # Whether to start and thus later shutdown, or just connect to ab existing server.
        self._manager = None  # The shared memory manager.
        self._shared_state = None

        self._manager = SharedMemoryManager(address=address, own=own)  # Instantiate the shared memory manager.
        # Either start it or just connect to an existing one.
        if self._own:
            self._manager.start()  # Shutdown in __del__().
        else:
            self._manager.connect()

        self._shared_state = getattr(self._manager, namespace)(timeout=timeout)

    def __enter__(self):
        return self._shared_state.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._shared_state.__exit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name):
        if name[0] == '_':
            return object.__getattribute__(self, name)
        return self._shared_state.__getattr__(name)

    def __setattr__(self, name, value):
        if name[0] == '_':
            return object.__setattr__(self, name, value)
        return self._shared_state.__setattr__(name, value)

    def __del__(self):
        if self._own:
            self._manager.shutdown()


# Restrict the device cache such that only linking is allowed. Once run_experiment() is called this gets swapped
# out for the unrestricted version that is context manged by Experiment.
devices = RestrictedDeviceCache()
