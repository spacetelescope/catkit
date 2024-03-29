from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument, InstrumentBaseProxy
from catkit.multiprocessing import SharedMemoryManager

"""Interface for a deformable mirror controller that can control 2 DMs.  
   It does so by interpreting the first half of the command for DM1, and the second for DM2.
   This controller cannot control the two DMs independently, it will always send a command to both."""


class DeformableMirrorController(Instrument, ABC):

    @abstractmethod
    def apply_shape_to_both(self, dm1_shape, dm2_shape):
        """Combines both commands and sends to the controller to produce a shape on each DM."""

    @abstractmethod
    def apply_shape(self, dm_shape, dm_num):
        """Forms a command for a single DM, with zeros padded for the DM not in use."""

    class PerformantProxy(InstrumentBaseProxy):
        """ WARNING: This is not implicitly thread safe. See InstrumentBaseProxy for details.

            NOTE: This proxy prevents referent introspection (aka attribute access) as InstrumentBaseProxy doesn't
            inherit from NamespaceProxy.
        """

        _method_to_typeid_ = {"__enter__": "DeformableMirrorControllerPerformantProxy"}

        def apply_shape_to_both(self, *args, **kwargs):
            return self._callmethod("apply_shape_to_both", args=args, kwds=kwargs)

        def apply_shape(self, *args, **kwargs):
            return self._callmethod("apply_shape", args=args, kwds=kwargs)


SharedMemoryManager.register("DeformableMirrorControllerPerformantProxy",
                             proxytype=DeformableMirrorController.PerformantProxy,
                             create_method=False)
