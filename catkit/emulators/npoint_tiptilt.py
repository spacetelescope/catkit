""" Interface for the nPoint Tip/Tilt closed-loop controller.
Connects to the controller via usb, and then sends and recieves hex
messages to send commands, check the status, and put error handling over
top.
"""

import logging
import os
import struct

from catkit.hardware.npoint.nPointTipTiltController import Commands, Parameters, NPointLC400
from catkit.interfaces.Instrument import SimInstrument


class PyvisaNpointEmulator:
    """nPointTipTilt connection class. 

    This nPointTipTilt class acts as a useful connection and storage vehicle 
    for commands sent to the nPoint FTDI LC400 controller. It has built in
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

        self.log = logging.getLogger()
        self.initialize()

    def initialize(self):
        self.value_store = {n: {var: 0 for var in Parameters} for n in NPointLC400.channels}
        self.response_message = []
        self.address_cursor = None
        self.message = None  # Used only for introspection, debugging, & testing.

    def ResourceManager(self, *args, **kwargs):
        """ On hardware, locates device. In simulation, returns itself so we can keep going."""
        self.log.info('SIMULATED NPointLC400 instantiated and logging online.')
        return self

    def open_resource(self, *args, **kwargs):
        return self

    def close(self, *args, **kwargs):
        self.initialize()

    def read_bytes(self, byte_count):
        """ On hardware, reads single message from device. In simulation, pulls most recent message that expected a response. """
        return self.response_message.pop()[:byte_count]

    def write_raw(self, message):
        """ On hardware, writes a single message from device. In simulation,
        updates logical stored values. """
        endian = NPointLC400.endian

        self.message = message

        #if not message.endswith(endpoint):
        #    raise ValueError(f"Corrupt data: message has incorrect endpoint.")

        # Parse message.
        command, parameter, address, channel, value = NPointLC400.parse_message(message)

        if command in (Commands.GET_SINGLE, Commands.GET_ARRAY, Commands.SET):
            self.address_cursor = (channel, parameter)

        # Set value or construct response ready for next read.
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
        elif command in (Commands.GET_SINGLE, Commands.GET_ARRAY):
            # Construct response message ready for it to be returned upon read.
            return_value = struct.pack(endian + parameter.data_type_fmt, self.value_store[channel][parameter])
            self.response_message.append(b''.join([command.value, address, return_value, NPointLC400.endpoint]))
            print("self.response_message", self.response_message)
        else:
            raise NotImplementedError(f'Non implemented command ({command}) found in message.')


class SimNPointLC400(SimInstrument, NPointLC400):
    """ Emulated version of the nPoint tip tilt controller. 
    Directly follows the npoint, except points to simlated USB connection
    library. """

    instrument_lib = PyvisaNpointEmulator

    def initialize(self, com_id, timeout=5):
        return super().initialize(com_id=com_id, timeout=timeout)
