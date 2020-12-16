import abc
from collections import namedtuple, UserDict
from collections.abc import Iterable
import copy
import warnings

from catkit.interfaces.Instrument import Instrument


class UserCache(UserDict, abc.ABC):
    @abc.abstractmethod
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

        def __del__(self):
            self.un_own()

        def __init__(self, device):
            object.__setattr__(self, "_owned_obj", device)
            # Open.
            self._owned_obj.__enter__()

        def __getattr__(self, name):
            return self._owned_obj.__getattribute__(name)

        def __setattr__(self, name, value):
            return object.__setattr__(self._owned_obj, name, value)

        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception_value, exception_traceback):
            pass

        def un_own(self):
            obj = self._owned_obj
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

    def load(self, key, *args, **kwargs):
        callback = self.callbacks.get(key)
        if callback is None:
            raise KeyError(f"The cache key '{key}' was either never decorated with auto_open() or adequate aliases weren't provided.")

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
