from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument, InstrumentBaseProxy
from catkit.multiprocessing import SharedMemoryManager
"""Abstract base class for all cameras. Implementations of this class also become context managers."""


class Camera(Instrument, ABC):

    @abstractmethod
    def take_exposures(self, exposure_time, num_exposures, path=None, filename=None, *args, **kwargs):
        """Takes exposures and should be able to save fits and simply return the image data."""

    @abstractmethod
    def stream_exposures(self, exposure_time, num_exposures, *args, **kwargs):
        """ Take a stream of exposures and yield individual images (ie. a generator)."""

    class Proxy(Instrument.Proxy):
        _method_to_typeid_ = Instrument.Proxy._method_to_typeid_.copy()
        _method_to_typeid_["__enter__"] = "CameraProxy"
        _method_to_typeid_["stream_exposures"] = "Iterator"

        # NOTE: The following shouldn't be necessary as it should be inherited from its base (WIP).
        # See comments regarding inheritance in catkit.multiprocessing.MutexedNamespaceAutoProxy.
        __enter__ = InstrumentBaseProxy.__enter__
        __exit__ = InstrumentBaseProxy.__exit__
        get_instrument_lib = Instrument.Proxy.get_instrument_lib
        instrument_lib = Instrument.Proxy.instrument_lib
        instrument = Instrument.Proxy.instrument


SharedMemoryManager.register("CameraProxy", proxytype=Camera.Proxy, create_method=False)
