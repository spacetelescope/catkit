import pyvisa

from catkit.interfaces.Instrument import Instrument


DEFAULT_POLL_TIMEOUT = 60  # This is not the comms timeout but that allowed for total polling duration (seconds).


class CommandEchoError(IOError):
    def __init__(self, cmd, echo):
        msg = f"The device responded with a command different from that sent. Expected: '{cmd}' got '{echo}'"
        super().__init__(msg)


class PyVisaInstrument(Instrument):

    instrument_lib = pyvisa.ResourceManager("@py")

    def read_all(self):
        """ Helper func for when read/writes are out of sync - consume all waiting reads until buffer is empty.
        :return list of read data.
        """

        data = []
        try:
            while True:
                data.append(self.instrument.read())
        except pyvisa.VisaIOError:
            pass
        return data

    def read_all_bytes(self):
        """ Helper func for when read/writes are out of sync - consume all waiting reads until buffer is empty.
        :return list of read data.
        """

        data = []
        try:
            while True:
                data.append(self.instrument.read_bytes(1))
        except pyvisa.VisaIOError:
            pass
        return data
