import platform
from catkit.config import CONFIG_INI
import pyvisa
import time

from catkit.interfaces.FilterWheel import FilterWheel


class ThorlabsFW102C(FilterWheel):
    """Abstract base class for filter wheels."""

    instrument_lib = pyvisa

    def initialize(self, *args, **kwargs):
        """ Initializes class instance, but doesn't -- and shouldn't -- open a connection to the hardware."""

        # Determine the os, and load the correct filter ID from the ini file.
        if platform.system().lower() == "darwin":
            self.visa_id = CONFIG_INI.get(self.config_id, "mac_resource_name")
        elif platform.system().lower() == "windows":
            self.visa_id = CONFIG_INI.get(self.config_id, "windows_resource_name")
        else:
            self.visa_id = CONFIG_INI.get(self.config_id, "windows_resource_name")

    def _open(self):
        """Open connection. Return an object connected to the instrument hardware.
        """
        rm = self.instrument_lib.ResourceManager('@py')

        # These values took a while to figure out; be careful changing them.
        return rm.open_resource(self.visa_id,
                                baud_rate=115200,
                                data_bits=8,
                                write_termination='\r',
                                read_termination='\r')

    def _close(self):
        self.instrument.close()

    def get_position(self):
        _bytes_written = self.instrument.write("pos?")

        if self.instrument.last_status is pyvisa.constants.StatusCode.success:

            # First read the echo to clear the buffer.
            self.instrument.read()

            # Now read the filter position, and convert to an integer.
            return int(self.instrument.read())
        else:
            raise Exception(f"Filter wheel '{self.config_id}' returned an unexpected response: '{self.instrument.last_status}'")

    def set_position(self, new_position):
        command = "pos=" + str(new_position)
        _bytes_written = self.instrument.write(command)  # bytes_written := len(command) + 1 due to '\r'.

        if self.instrument.last_status is pyvisa.constants.StatusCode.success:
            self.instrument.read()
            # Wait for wheel to move. Fairly arbitrary 3 s delay...
            time.sleep(3)
        else:
            raise Exception(f"Filter wheel '{self.config_id}' returned an unexpected response: '{self.instrument.last_status}'")

    def ask(self, write_string):
        self.instrument.write(write_string)

    def read(self):
        return self.instrument.read()

    def flush(self):
        print(self.instrument.read_bytes(1))
