from abc import ABC, abstractmethod

import pyvisa

import catkit.hardware.thorlabs.ThorlabsFW102C


class FW102CEmulator(ABC):
    """ Emulates pyvisa specifically for the FW102C. """

    Commands = catkit.hardware.thorlabs.ThorlabsFW102C.ThorlabsFW102C.Commands

    class constants:
        class StatusCode:
            success = pyvisa.constants.StatusCode.success

    def __init__(self):
        self.last_status = self.constants.StatusCode.success
        self.position = 1

    def ResourceManager(self, *args, **kwargs):
        return self

    def open_resource(self, *args, **kwargs):
        return self

    def close(self):
        pass

    @abstractmethod
    def move_filter(self, position):
        """ Implement to make filter changes for the simulated system, e.g., a Poppy model. """
        pass

    def write(self, data):
        if self.Commands.GET_POSITION.value in data:
            return
        elif self.Commands.SET_POSITION.value in data:
            new_position = int(data.split(self.Commands.SET_POSITION.value)[1])
            if 1 < new_position > 6:
                raise ValueError(f"Position must be 1-6 (not '{new_position}')")
            self.position = new_position
            self.move_filter(new_position)
        else:
            raise NotImplementedError

    def read(self):
        return str(self.position)
