""" Interface for the nPoint Tip/Tilt closed-loop controller.
Connects to the controller via usb, and then sends and recieves hex
messages to send commands, check the status, and put error handling over
top.
"""

import logging
import struct

from catkit.hardware.npoint.nPointTipTiltController import Commands, Parameters, NPointTipTiltController
from catkit.interfaces.Instrument import SimInstrument


class EmulatedLibUSB:
    @staticmethod
    def get_backend(find_library=None):
        pass


class PyusbNpointEmulator:
    """nPointTipTilt connection class. 

    This nPointTipTilt class acts as a useful connection and storage vehicle 
    for commands sent to the nPoint FTID LC400 controller. It has built in 
    functions that allow for writing commands, checking the status, etc. 
    By instantiating the nPointTipTilt object you find the LC400 controller 
    and set the default configuration. Memory managers in the back end 
    should close the connection when the time is right.
    """

    config_params = ('< SIMULATED CONFIGUARTION 1: 0 mA>',)

    def __init__(self):
        """ Since we'll need to respond as if commands are being sent and we
        can read values, this is where we'll initialize some value stores that
        will get sent in emulated messages. """

        self.log = logging.getLogger(f"{self.__module__}.{self.__class__.__qualname__}")

        self.value_store = {n: {var: 0 for var in Parameters} for n in NPointTipTiltController.channels}
        self.response_message = []
        self.address_cursor = None
        self.message = None  # Used only for introspection, debugging, & testing.

    def find(self, find_all=False, backend=None, custom_match=None, **args):
        """ On hardware, locates device. In simulation, returns itself so we can keep going."""
        self.log.info('SIMULATED nPointTipTilt instantiated and logging online.')
        return self

    def __iter__(self):
        """ Simulated iteration to appeal to the ability to check the configuration modes with `get_config`. """
        for cfg in self.config_params:
            yield cfg
    
    def set_configuration(self, configuration=None):
        """ On hardware, sets nPoint to its default configuration. In simulation, no behavior necessary."""
        if configuration is not None:
            raise NotImplementedError("We don't have the ability to set or simulate non-default configuration.")

    def read(self, endpoint, message_length, timeout):
        """ On hardware, reads single message from device. In simulation, pulls most recent message that expected a response. """
        return self.response_message.pop()

    def write(self, endpoint, message, timeout):
        """ On hardware, writes a single message from device. In simulation,
        updates logical stored values. """
        endian = NPointTipTiltController.endian

        self.message = message

        #if not message.endswith(endpoint):
        #    raise ValueError(f"Corrupt data: message has incorrect endpoint.")

        # Parse message.
        command, parameter, address, channel, value = NPointTipTiltController.parse_message(message)

        if command in (Commands.GET, Commands.SET):
            self.address_cursor = (channel, parameter)

        if command is Commands.SET:
            self.value_store[channel][parameter] = value
        elif command is Commands.SECOND_MSG:
            # If we wanted to emulator the hardware correctly, this would increment the address cursor and write the
            # value to that. However, it's easier and completely within the bounds of our current usage to just...
            # Concat previously stored value with new.
            channel, parameter = self.address_cursor
            stored_value = self.value_store[channel][parameter]
            if not isinstance(stored_value, int):
                raise ValueError(f"Expected to append to int value and not '{type(stored_value)}'")
            first_32b = struct.pack(endian + 'I', self.value_store[channel][parameter])
            second_32b = struct.pack(endian + 'I', value)
            self.value_store[channel][parameter] = struct.unpack(endian + 'd', first_32b + second_32b)[0]
        elif command is Commands.GET:
            # Construct response message ready for it to be returned upon read.
            n_reads = value
            if n_reads == 1:
                data_type_fmt = 'I'
            elif n_reads == 2:
                data_type_fmt = 'd'
            else:
                raise NotImplementedError(f"Supports only 32b ints and 64b floats. Received {n_reads * 32}b data block.")
            return_value = struct.pack(endian + data_type_fmt, self.value_store[channel][parameter])
            self.response_message.append(b''.join([Commands.GET.value, address, return_value, NPointTipTiltController.endpoint]))
        else:
            raise NotImplementedError(f'Non implemented command ({command}) found in message.')


class SimNPointTipTiltController(SimInstrument, NPointTipTiltController):
    """ Emulated version of the nPoint tip tilt controller. 
    Directly follows the npoint, except points to simlated USB connection
    library. """

    instrument_lib = PyusbNpointEmulator
    library_mapping = {'libusb0': EmulatedLibUSB, 'libusb1': EmulatedLibUSB}
