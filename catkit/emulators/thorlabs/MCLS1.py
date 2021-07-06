import catkit.hardware.thorlabs.ThorlabsMCLS1
from catkit.interfaces.Instrument import SimInstrument


class MCLS1Emulator:
    """ Emulates UART comms library specifically for the MCLS1. """

    N_CHANNELS = 4  # The MCLS1 has only 4 channels.

    Command = catkit.hardware.thorlabs.ThorlabsMCLS1.ThorlabsMCLS1.Command

    def __init__(self, device_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instrument_handle = False
        self.active_channel = None
        self.system_enabled = False
        self.channel_enabled = [False] * self.N_CHANNELS
        self.current = [0] * self.N_CHANNELS
        self.port = None
        self.device_id = device_id

    def fnUART_LIBRARY_open(self, port, *args, **kwargs):
        self.instrument_handle = True
        self.port = port
        return self.instrument_handle

    def fnUART_LIBRARY_isOpen(self, port, *args, **kwargs):
        self.instrument_handle = True
        return self.instrument_handle

    def fnUART_LIBRARY_close(self, handle, *args, **kwargs):
        self.instrument_handle = False

    def fnUART_LIBRARY_Set(self, handle, command, size, *args, **kwargs):
        if not self.instrument_handle:
            raise RuntimeError("Connection closed")

        command = command.decode()

        if "=" not in command:
            raise RuntimeError(f"Expected SET command ('=') but got '{command}'")

        command, value = command.replace(self.Command.TERM_CHAR.value, '').split("=")
        command += "="
        command = self.Command(command)

        if command is self.Command.SET_SYSTEM:
            self.system_enabled = bool(int(value))
        elif command is self.Command.SET_CHANNEL:
            self.active_channel = int(value)
        elif command is self.Command.SET_ENABLE:
            self.channel_enabled[self.active_channel-1] = bool(int(value))
        elif command is self.Command.SET_CURRENT:
            self.current[self.active_channel-1] = float(value)
        else:
            raise NotImplementedError

        self.set_sim(command)  # Propagate changes through to simulator.

    def fnUART_LIBRARY_Get(self, handle, command, buffer, *args, **kwargs):
        if not self.instrument_handle:
            raise RuntimeError("Connection closed")

        command = command.decode().replace(self.Command.TERM_CHAR.value, '')

        if "?" not in command:
            raise RuntimeError(f"Expected GET command ('?') but got '{command}'")

        command = self.Command(command)

        if command is self.Command.GET_CURRENT:
            resp = float(self.current[self.active_channel-1])
        elif command is self.Command.GET_ENABLE:
            resp = int(self.channel_enabled[self.active_channel-1])
        elif command is self.Command.GET_CHANNEL:
            resp = int(self.active_channel)
        else:
            raise NotImplementedError

        resp = str(resp).encode()
        buffer[:len(resp)] = resp

    def fnUART_LIBRARY_list(self, buffer, size, *args, **kwargs):
        resp = f"0, {self.device_id}".encode()  # port, ID.
        buffer[:len(resp)] = resp

    def set_sim(self, command):
        """ Override this to interface with simulator, e.g., a Poppy model. """


class MCLS1(SimInstrument, catkit.hardware.thorlabs.ThorlabsMCLS1.ThorlabsMCLS1):
    instrument_lib = MCLS1Emulator
