from collections import namedtuple, UserDict
from enum import Enum
from functools import lru_cache
from multiprocess.managers import AcquirerProxy, BaseProxy, DictProxy
import warnings

from catkit.interfaces.Instrument import Instrument
from catkit.multiprocessing import MutexedNamespace, SharedMemoryManager, MutexedNamespaceSingleton


class UserCache(UserDict):
    def load(self, key, *args, **kwargs):
        """ Func to load non-existent cache entries. Is designed to be overridden. """
        raise KeyError(key)

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
    def __delitem__(self, key):
        if hasattr(self.data[key], "__exit__"):
            try:
                self.data[key].__exit__(None, None, None)
            except Exception:
                warnings.warn(f"{key} failed to exit.")
        del self.data[key]

    def __del__(self):
        self.clear()


class MutexedDict(MutexedNamespace, UserCache):
    """ Effectively MutexedDict with auto load functionality. """

    # def __init__(self, *args, lock=None, timeout=None, **kwargs):
    #     super(MutexedDict, self).__init__(lock=lock, timeout=timeout)
    #     super(UserCache, self).__init__(*args, **kwargs)

    def __contains__(self, *args, **kwargs):
        with self._catkit_mutex:
            return super().__contains__(*args, **kwargs)

    def __delitem__(self, *args, **kwargs):
        with self._catkit_mutex:
            return super().__delitem__(*args, **kwargs)

    def __getitem__(self, *args, **kwargs):
        with self._catkit_mutex:
            return super().__getitem__(*args, **kwargs)

    def __iter__(self, *args, **kwargs):
        with self._catkit_mutex:
            return super().__iter__(*args, **kwargs)

    def __len__(self, *args, **kwargs):
        with self._catkit_mutex:
            return super().__len__(*args, **kwargs)

    def __setitem__(self, *args, **kwargs):
        with self._catkit_mutex:
            return super().__setitem__(*args, **kwargs)

    def clear(self, *args, **kwargs):
        with self._catkit_mutex:
            return super().clear(*args, **kwargs)

    def copy(self, *args, **kwargs):
        # TODO: test this.
        with self._catkit_mutex:
            # Copy dict-wise
            copy = type(self)(self.data.copy())
            # Copy namespace-wise
            copy.copy_from(self)
            return copy

    def get(self, *args, **kwargs):
        with self._catkit_mutex:
            return super().get(*args, **kwargs)

    # NOTE: has_key() has been deprecated.
    # def has_key(self, *args, **kwargs):
    #     with self._catkit_mutex:
    #         return super().has_key(*args, **kwargs)

    def items(self, *args, **kwargs):
        # NOTE: In the interest of thread-safety this returns a list instead of a dict view. However, also note that
        # a race condition exists between getting this data and a subsequent dict query.
        with self._catkit_mutex:
            return list(super().items(*args, **kwargs))

    def keys(self, *args, **kwargs):
        # NOTE: In the interest of thread-safety this returns a list instead of a dict view. However, also note that
        # a race condition exists between getting this data and a subsequent dict query.
        with self._catkit_mutex:
            return list(super().keys(*args, **kwargs))

    def pop(self, *args, **kwargs):
        with self._catkit_mutex:
            return super().pop(*args, **kwargs)

    def popitem(self, *args, **kwargs):
        with self._catkit_mutex:
            return super().popitem(*args, **kwargs)

    def setdefault(self, *args, **kwargs):
        with self._catkit_mutex:
            return super().setdefault(*args, **kwargs)

    def update(self, *args, **kwargs):
        with self._catkit_mutex:
            return super().update(*args, **kwargs)

    def values(self, *args, **kwargs):
        # NOTE: In the interest of thread-safety this returns a list instead of a dict view. However, also note that
        # a race condition exists between getting this data and a subsequent dict query.
        with self._catkit_mutex:
            return list(super().values(*args, **kwargs))

    class Proxy(MutexedNamespace.Proxy, DictProxy):
        _exposed_ = (*AcquirerProxy._exposed_, *DictProxy._exposed_)


class NestedMutexedDictProxy(MutexedDict.Proxy):
    """ Assumes and requires all dict items to be themselves dicts. """
    _method_to_typeid_ = {**MutexedDict.Proxy._method_to_typeid_, "__getitem__": "MutexedDictProxy"}


# This will get nuked once all hardware adheres to the Instrument interface.
def set_keep_alive(device, value):
    if isinstance(device, Instrument):
        device._Instrument__keep_alive = value
        if not value:
            device._context_counter = 0
    else:
        device._keep_alive = value


class DeviceCache(MutexedDict):

    Callback = namedtuple("callback", ["func", "root_key", "aliases"])

    aliases = {}
    callbacks = {}

    def __enter__(self):
        self.clear()  # This may not be desirable to all users.
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.clear()

    def __del__(self):
        self.clear()

    def get(self, key, *args, **kwargs):
        key = key.name if isinstance(key, DeviceCacheEnum) else key
        return super().get(key, *args, **kwargs)

    def pop(self, key, *args, **kwargs):
        key = key.name if isinstance(key, DeviceCacheEnum) else key
        return super().pop(key, *args, **kwargs)

    def __delitem__(self, key):
        key = key.name if isinstance(key, DeviceCacheEnum) else key

        # Deleting the device won't close it if external references exist, this must be done explicitly.
        obj = self[key]
        set_keep_alive(obj, False)

        # Explicitly reset context counter to force closure.
        if hasattr(obj, "_context_counter"):
            obj._context_counter = 0

        # Close.
        try:
            obj.__exit__(None, None, None)
        except Exception:
            raise
            # Don't raise so that other devices can exit.
            warnings.warn(f"{obj.config_id} failed to close correctly.")
        finally:
            pass

        super().__delitem__(key)

    def __contains__(self, item):
        item = item.name if isinstance(item, DeviceCacheEnum) else item
        return super().__contains__(item)

    def __getitem__(self, item):
        item = item.name if isinstance(item, DeviceCacheEnum) else item
        try:
            return super().__getitem__(item)
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
                return self[item]
            else:
                return ret

    def __setitem__(self, key, value):
        key = key.name if isinstance(key, DeviceCacheEnum) else key

        def raise_on_collision(obj_a, obj_b):
            nonlocal key
            # Raise on collision but only if they're NOT the same underlying object.
            if obj_a is not obj_b:
                raise KeyError(f"Cache collision: '{key}' key already exists in device cache.")

        if key in self.data:
            raise_on_collision(super().__getitem__(key), value)
        elif key in self.aliases:
            raise_on_collision(self.aliases[key], value)
        else:
            super().__setitem__(key, value)
            self[key].__enter__()
            assert self[key].is_open()

    def open_all(self):
        if not self.callbacks:
            return

        for callback in self.callbacks.values():
            #self.__getitem__(callback.root_key)
            self[callback.root_key]
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
        # NOTE: The device is opened in self.__setitem__
        self.update({key: callback.func()})
        assert key in self

        # Register aliases.
        aliases = callback.aliases
        if aliases:
            for alias in aliases:
                # Check for collisions.
                if alias in self.aliases:
                    raise KeyError(f"Cache collision: '{alias}' key already exists in device cache.")
                self.aliases[alias] = super().__getitem__(key)

    def link(self, key, aliases=None):
        """ Decorator for testbed device funcs to automatically cache them. """

        key = key.name if isinstance(key, DeviceCacheEnum) else key

        def decorator(func):
            def wrapper(*args, **kwargs):
                nonlocal self
                # Return cached instances if present.
                try:
                    if key in self:  # __contains__ doesn't call __getitem__ so won't auto load on miss.
                        return self[key]
                    #return self.data[key]  # Only possible if a previous cache access occurred.
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


class SharedSingletonDeviceCache(MutexedNamespaceSingleton, DeviceCache):
    instance = None

    @classmethod
    def factory(cls, address=None, name=None, timeout=None):
        # NOTE: This has limited use with a spawned context due to bug when pickling abstract derived types,
        # such as this one (via UserDict).
        return super().factory(address=address, name=name, timeout=timeout, new_class_dict=dict(callbacks={},
                                                                                                aliases={}))

    @classmethod
    def link(cls, key, aliases=None):
        """ Decorator for testbed device funcs to automatically cache them. """

        key = key.name if isinstance(key, DeviceCacheEnum) else key

        def decorator(func):
            # Register callback to be called upon a cache miss. Register func and not wrapper to avoid future pretzeling.
            cls.callbacks[key] = cls.Callback(func=func, root_key=key, aliases=aliases)
            if aliases:
                for alias in aliases:
                    # Check for collisions.
                    if alias in cls.callbacks:
                        raise KeyError(f"Cache collision: '{alias}' key already exists in device cache.")
                    cls.callbacks[alias] = cls.Callback(func=func, root_key=key, aliases=None)

            def wrapper(*args, **kwargs):
                nonlocal cls
                # Return cached instances if present.
                if key in cls():
                    return cls()[key]

                # Call func.
                ret = func(*args, **kwargs)

                # Don't automatically cache, if the user wants it cached they need to access via the cache itself.
                #self.update({key: ret})
                return ret
            return wrapper
        return decorator

    class Proxy(MutexedNamespaceSingleton.Proxy, DictProxy):
        # Have items (devices) returned from the remote server be proxies such that their attributes & methods
        # will be updated and called on the server.
        # The proxy type is that of catkit.interfaces.Instrument.Instrument.Proxy which is registered with the manager
        # in its module as the str "InstrumentAutoProxy".
        _method_to_typeid_ = {"__getitem__": "InstrumentProxy",
                              "get": "InstrumentProxy",
                              "pop": "InstrumentProxy",
                              "popitem": "InstrumentProxy",
                              **MutexedNamespaceSingleton.Proxy._method_to_typeid_,
                              **DictProxy._method_to_typeid_}
        _exposed_ = (*MutexedNamespaceSingleton.Proxy._exposed_, *DictProxy._exposed_)

        def __getitem__(self, item):
            # We don't want to send the enum member as it contains a ref to the cache
            item = item.name if isinstance(item, DeviceCacheEnum) else item
            return super().__getitem__(item)

        def __setitem__(self, item, value):
            # We don't want to send the enum member as it contains a ref to the cache
            item = item.name if isinstance(item, DeviceCacheEnum) else item
            return super().__setitem__(item, value)

        def __delitem__(self, item):
            # We don't want to send the enum member as it contains a ref to the cache
            item = item.name if isinstance(item, DeviceCacheEnum) else item
            return super().__delitem__(item)

        def values(self):
            """ DictProxy returns a list instead of a view, as does this. """
            lst = []
            for key in self:
                lst.append(self[key])
            return lst

        def items(self):
            """ DictProxy returns a list instead of a view, as does this. """
            values = self.values()
            keys = self.keys()
            return list(zip(keys, values))


class DeviceCacheEnum(Enum):
    """ Enum API to DeviceCache. """

    def __init__(self, description, config_id, cache=None):
        self.description = description
        self.config_id = config_id

        # Use the default cache identifier if None.
        self.cache = self.default_cache() if cache is None else cache
        self.cache_type = self.cache if isinstance(self.cache, type) else type(self.cache)

        # Local cache for caching proxies when using shared memory.
        self.using_shared_memory = False#isinstance(self.cache_type, SharedSingletonDeviceCache)

        # Needs to be last entry to this code block.
        # It prevents __getattr__ and __setattr__ pointing through to the cache prior to this line.
        self.__object_exists = True

    def link(self, aliases=None):
        return getattr(self, "cache").link(key=getattr(self, "name"), aliases=aliases)

    @classmethod
    def open_all(cls):
        for device in cls:
            assert device().is_open()

    @staticmethod
    def default_cache():
        """ Can be overridden.
            This provides an easy way to specify the default cache without needing to do so explicitly for each member
        """
        global devices
        return devices

    # Cache the results from the device cache to avoid checking for cache activation and rebuilding proxies etc.
    # NOTE: It's possible that the proxy has been removed from the remote cache.
    @lru_cache(maxsize=None)
    def get_device(self, name):
        object.__getattribute__(self, "activate_cache")()
        cache = object.__getattribute__(self, "cache")
        return cache[name]

    @classmethod
    @lru_cache(maxsize=None)
    def _missing_(cls, value):
        """ Allow lookup by config_id, such that DeviceCacheEnum(config_id) returns its matching member. """
        if isinstance(value, DeviceCacheEnum):
            value = value.config_id

        for item in cls:
            if value in (item.config_id, item.description):
                # TODO: should really test cache equivalence.
                return item

    # def __getstate__(self):
    #     """ Remove cache proxy before pickling. """
    #     if not isinstance(self.cache, BaseProxy):
    #         return self
    #
    #     import copy
    #     obj = copy.copy(self)  # Shallow copy.
    #     obj.cache = obj.cache_type
    #     return obj

    def __call__(self):
        return self.get_device(object.__getattribute__(self, "name"))

    def is_open(self):
        cache = object.__getattribute__(self, "cache")
        if cache is None or isinstance(cache, type):
            return False

        if self.name in self.cache:
            return self.cache[self.name].is_open() is not None
        else:
            return False

    # Override base Instrument context to manage mutex rather than device open & close.
    def __enter__(self):
        """ DeviceCacheEnum.member.cache[member].acquire() """
        return self.__getattr__("acquire")()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """ DeviceCacheEnum.member.cache[member].release() """
        return self.__getattr__("release")()

    # Since Python doesn't allow for function overloading, we can only have one set of context managers and mutex funcs.
    # These can either be classmethods or an instance methods
    # I.e., member.cache.acquire() or member.cache[member].acquire.

    # Using with stmnts per instrument, rather than per enum class, would require the user to write far less boiler
    # plate code than the alternative (as implemented above).
    # However, for example, if acquire() and release() are classmethods of the enum, __getattribute__() will never call
    # __getattr__ and thus enum.member.acquire() := enum.acquire() as enum.member.acquire() won't poke through to call
    # Instrument.Proxy.acquire(). This equivalence would be grossly misleading and thus prevents us from having a
    # classmethod of this nature at all, as enum.member.acquire() would act on the entire class (see below commented out
    # implementation.

    # @classmethod
    # def acquire(cls, *args, **kwargs):
    #     all_locked = True
    #     for member in cls:
    #         all_locked &= member.cache.acquire(*args, **kwargs)
    #     return all_locked
    #
    # @classmethod
    # def release(cls):
    #     for member in cls:
    #         member.cache.release()

    def activate_cache(self, *args, **kwargs):
        cache = object.__getattribute__(self, "cache")
        if cache is None or isinstance(cache, type):
            cache_type = object.__getattribute__(self, "cache_type")
            object.__setattr__(self, "cache",  cache_type(*args, **kwargs))

    @classmethod
    def reset(cls):
        for member in cls:
            object.__setattr__(member, "cache", None)

    # NOTES on __getattr__ & __setattr__:
    # The functionality of poking through the enum to the cache needs to be delayed beyond enum creation such that the
    # server can be started and other flags (making shared memory usage optional) can be correctly set. This is achieved
    # using two patterns.
    # 1) __getattr__: (noting that this is only called if the attribute doesn't already exist) any protected attr
    #    (those with a leading "_") belong to the enum, otherwise it pokes through to the cache.
    # 2) __setattr__: The same is true as is for __getattr__ however, this logic is deferred until __ini__ returns. This
    #    is so the desired member values can be set.
    # The caveat with the underscore pattern is that it is that also used by multiprocess.managers.BaseProxy and
    # therefore proxy attrs (not referent attrs) won't be accessible via the enum API, e.g., Device.CAMERA._getvalue().
    # Instead, the actual proxy would first have to be retrieved, e.g., Device.CAMERA()._getvalue().

    def __getattr__(self, item):
        """ Allow DeviceCacheEnum.member.attribute -> DeviceCacheEnum.member.cache[member].attribute """
        if item[0] == "_":
            return object.__getattribute__(self, item)
        else:
            device = self.get_device(object.__getattribute__(self, "name"))
            return getattr(device, item)

    def __setattr__(self, name, value):
        """ Allow DeviceCacheEnum.member.attribute = value -> DeviceCacheEnum.member.cache[member].attribute = value """
        if object.__getattribute__(self, "__dict__").get("_DeviceCacheEnum__object_exists", None) and name[0] != "_":
            device = self.get_device(self.name)
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
        object.__setattr__(self, "__lock", False)  # Unlock such that super().__init__() has access.
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "__lock", True)
        object.__setattr__(self, "__unrestricted", ("aliases", "Callback", "callbacks", "link", "__name__", "__class__",
                                               "_catkit_mutex"))

    def __getattribute__(self, item):
        if (object.__getattribute__(self, "__lock") and
                item not in object.__getattribute__(self, "__unrestricted")):
            raise NameError(f"Access to '{item}' is restricted The device cache can only be used from a running experiment.")
        return super().__getattribute__(item)

    def __setattr__(self, item, value):
        if (object.__getattribute__(self, "__lock") and
                item not in object.__getattribute__(self, "__unrestricted")):
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


# Restrict the device cache such that only linking is allowed. Once run_experiment() is called this gets swapped
# out for the unrestricted version that is context manged by Experiment.
devices = RestrictedDeviceCache()

# Register shared types.
SharedMemoryManager.register("MutexedDict", callable=MutexedDict, proxytype=MutexedDict.Proxy, create_method=True)

# Register proxies.
SharedMemoryManager.register("MutexedDictProxy", proxytype=MutexedDict.Proxy, create_method=False)
SharedMemoryManager.register("NestedMutexedDictProxy", proxytype=NestedMutexedDictProxy, create_method=False)
