import functools
import itertools
import os
import struct

import pytest

from catkit.hardware.npoint.nPointTipTiltController import Commands, Parameters, NPointLC400
from catkit.emulators.npoint_tiptilt import SimNPointLC400


Controller = functools.partial(SimNPointLC400,
                               config_id="npoint_tiptilt_lc_400",
                               com_id="dummy")


def test_init():
    Controller()


def test_get_status():
    with Controller() as controller:
        for channel in controller.channels:
            controller.get_status(channel)


@pytest.mark.parametrize(("parameter", "channel", "value"),
                         itertools.product([param for param in Parameters],
                                           [channel for channel in NPointLC400.channels],
                                           [value for value in (0, 1)]))
def test_set(parameter, channel, value):
    with Controller() as controller:
        controller.set(parameter, channel, value)
        assert value == controller.instrument_lib.value_store[channel][parameter]


@pytest.mark.parametrize(("parameter", "channel"),
                         itertools.product([param for param in Parameters],
                                           [channel for channel in NPointLC400.channels]))
def test_get(parameter, channel):
    with Controller() as controller:
        assert controller.get(parameter, channel) == 0


@pytest.mark.parametrize(("parameter", "channel", "value"),
                         itertools.product([param for param in Parameters],
                                           [channel for channel in NPointLC400.channels],
                                           [value for value in (0, 1)]))
def test_set_and_check(parameter, channel, value):
    with Controller() as controller:
        controller.set(parameter, channel, value)


@pytest.mark.parametrize("value", (True, False))
def test_set_closed_loop(value):
    with Controller() as controller:
        controller.set_closed_loop(value)


@pytest.mark.parametrize(("command", "parameter", "channel", "value"),
                         itertools.product([command for command in (Commands.SET, Commands.GET_ARRAY)],
                                           [param for param in Parameters],
                                           [channel for channel in NPointLC400.channels],
                                           [value for value in (0, 1)]))
def test_message_parser(command, parameter, channel, value):
    address = NPointLC400.build_address(parameter, channel)
    byte_value = struct.pack(NPointLC400.endian + 'I', value)
    message = b''.join([command.value, address, byte_value, NPointLC400.endpoint])

    parsed_command, parsed_parameter, parsed_address, parsed_channel, parsed_value = NPointLC400.parse_message(message)

    assert parsed_command is command
    assert parsed_parameter is parameter
    assert parsed_address == address
    assert parsed_channel == channel
    assert parsed_value == value
