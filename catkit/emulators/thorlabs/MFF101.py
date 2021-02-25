from abc import ABC, abstractmethod

import catkit.hardware.thorlabs.ThorlabsMFF101


class MFF101Emulator(ABC):
    """ Emulates ftd2xx specifically for the MFF101. """

    class defines:
        BITS_8 = None
        STOP_BITS_1 = None
        PARITY_NONE = None
        FLOW_RTS_CTS = None

    def __init__(self, config_id, in_beam_position):
        self.config_id = config_id
        self.in_beam_position = in_beam_position

    def openEx(self, id_str, flags=None):
        return self

    def setBaudRate(self, baud):
        pass

    def setDataCharacteristics(self, wordlen, stopbits, parity):
        pass

    def purge(self, mask=0):
        pass

    def resetDevice(self):
        pass

    def setFlowControl(self, flowcontrol, xon=-1, xoff=-1):
        pass

    def setRts(self):
        pass

    def close(self):
        pass

    @abstractmethod
    def move_to_position_1(self):
        pass

    @abstractmethod
    def move_to_position_2(self):
        pass

    def write(self, data):
        if data == catkit.hardware.thorlabs.ThorlabsMFF101.ThorlabsMFF101.Command.MOVE_TO_POSITION_1.value:
            self.move_to_position_1()
        elif data == catkit.hardware.thorlabs.ThorlabsMFF101.ThorlabsMFF101.Command.MOVE_TO_POSITION_2.value:
            self.move_to_position_2()
        elif data == catkit.hardware.thorlabs.ThorlabsMFF101.ThorlabsMFF101.Command.BLINK_LED.value:
            pass
        else:
            raise NotImplementedError
