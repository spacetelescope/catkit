from abc import ABC, abstractmethod

"""Interface for backup power supply (ex: UPS)"""


class BackupPower(ABC):
    # Abstract Methods.
    @abstractmethod
    def get_status(self):
        """Queries backup power and reports status. Returns whatever format the device uses."""

    @abstractmethod
    def is_power_ok(self):
        """Boolean function to determine whether the system should initiate a shutdown."""
