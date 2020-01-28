from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument
"""Interface for a segmented deformable mirror controller.
"""


class SegementedDeformableMirrorController(Instrument, ABC):

    @abstractmethod
    def apply_shape(self, shape):
        """Forms a command for a single DM, with zeros padded for the DM not in use."""
