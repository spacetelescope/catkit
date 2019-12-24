from abc import ABC, abstractmethod

from catkit.interfaces.Instrument import Instrument
"""Interface for a deformable mirror controller that can control 2 DMs.  
   It does so by interpreting the first half of the command for DM1, and the second for DM2.
   This controller cannot control the two DMs independently, it will always send a command to both."""


class TemperaturePressureSensor(Instrument, ABC):
    
    @abstractmethod
    def check_temperature_pressue(self):
        """Checks for temperature and pressure."""
