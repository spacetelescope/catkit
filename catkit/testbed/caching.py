from abc import abstractmethod, ABC
from collections import namedtuple, UserDict
from enum import Enum
import warnings

from catkit.interfaces.Instrument import Instrument


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


class ContextCache(UserCache):
    """ Cache of context managed items (non device/instrument). """
    def load(self, key, *args, **kwargs):
        pass

    def __delitem__(self, key):
        try:
            self.data[key].__exit__(None, None, None)
        except Exception:
            warnings.warn(f"{key} failed to exit.")
        del self.data[key]

    def __del__(self):
        self.clear()


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

    @classmethod
    def _missing_(cls, value):
        """ Allow lookup by config_id, such that DeviceCacheEnum(config_id) returns its matching member. """
        for item in cls:
            if value == item.config_id:
                return item

    def __getattr__(self, item):
        global devices
        """ Allow DeviceCacheEnum.member.attribute -> catkit.testbed.devices[member].attribute """
        config_id = object.__getattribute__(self, "config_id")
        member = self.__class__(config_id)
        device = devices[member]
        return device.__getattribute__(item)


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
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.clear()
        super().__setattr__("__lock", True)

    def __del__(self):
        super().__setattr__("__lock", False)
        self.clear()


# Restrict the device cache such that only linking is allowed. Once run_experiment() is called this gets swapped
# out for the unrestricted version that is context manged by Experiment.
devices = RestrictedDeviceCache()
