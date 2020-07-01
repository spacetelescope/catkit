import functools
import itertools
import os
import struct

import pytest

from catkit.hardware.npoint.nPointTipTiltController import Commands, Parameters, NPointTipTiltController
from catkit.emulators.npoint_tiptilt import SimNPointTipTiltController

vendor_id = 1027
product_id = 24596


Controller = functools.partial(SimNPointTipTiltController,
                               config_id="npoint_tiptilt_lc_400",
                               vendor_id=vendor_id,
                               product_id=product_id,
                               library_path=os.path.abspath(__file__))


def test_init():
    Controller()


def test_get_status():
    with Controller() as controller:
        for channel in controller.channels:
            controller.get_status(channel)


@pytest.mark.parametrize(("parameter", "channel", "value"),
                         itertools.product([param for param in Parameters],
                                           [channel for channel in NPointTipTiltController.channels],
                                           [value for value in (0, 1)]))
def test_set(parameter, channel, value):
    with Controller() as controller:
        controller.set(parameter, channel, value)
        assert value == controller.instrument_lib.value_store[channel][parameter]


@pytest.mark.parametrize(("parameter", "channel"),
                         itertools.product([param for param in Parameters],
                                           [channel for channel in NPointTipTiltController.channels]))
def test_get(parameter, channel):
    with Controller() as controller:
        assert controller.get(parameter, channel) == 0


@pytest.mark.parametrize(("parameter", "channel", "value"),
                         itertools.product([param for param in Parameters],
                                           [channel for channel in NPointTipTiltController.channels],
                                           [value for value in (0, 1)]))
def test_set_and_check(parameter, channel, value):
    with Controller() as controller:
        controller.set(parameter, channel, value)


@pytest.mark.parametrize("value", (True, False))
def test_set_closed_loop(value):
    with Controller() as controller:
        controller.set_closed_loop(value)


@pytest.mark.parametrize(("command", "parameter", "channel", "value"),
                         itertools.product([command for command in (Commands.SET, Commands.GET)],
                                           [param for param in Parameters],
                                           [channel for channel in NPointTipTiltController.channels],
                                           [value for value in (0, 1)]))
def test_message_parser(command, parameter, channel, value):
    address = NPointTipTiltController.build_address(parameter, channel)
    byte_value = struct.pack(NPointTipTiltController.endian + 'I', value)
    message = b''.join([command.value, address, byte_value, NPointTipTiltController.endpoint])

    parsed_command, parsed_parameter, parsed_address, parsed_channel, parsed_value = NPointTipTiltController.parse_message(message)

    assert parsed_command is command
    assert parsed_parameter is parameter
    assert parsed_address == address
    assert parsed_channel == channel
    assert parsed_value == value


@pytest.mark.parametrize(("parameter", "channel"),
                         itertools.product([param for param in Parameters],
                                           [channel for channel in NPointTipTiltController.channels]))
def test_address(parameter, channel):
    with Controller() as controller:
        new_address = SimNPointTipTiltController.build_address(parameter, channel)
        cmd_key = parameter.name.lower()
        cmd_type = "get"  # Irrelevant as it's not apart of the address.
        assert new_address == controller._build_message(cmd_key, cmd_type, channel)[0][1:5]


@pytest.mark.skip
@pytest.mark.parametrize(("parameter", "channel"),
                         itertools.product([param for param in Parameters],
                                           [channel for channel in NPointTipTiltController.channels]))
def test_get(parameter, channel):
    with Controller() as controller:
        controller.get(parameter, channel)
        cmd_key = parameter.name.lower()
        cmd_type = "get"  # Irrelevant as it's not apart of the address.
        assert controller.instrument_lib.message == controller._build_message(cmd_key, cmd_type, channel)[0]


@pytest.mark.skip
@pytest.mark.parametrize(("parameter", "channel", "value"),
                         itertools.product([param for param in Parameters],
                                           [channel for channel in NPointTipTiltController.channels],
                                           [value for value in (0, 1)]))
def test_set(parameter, channel, value):
    with Controller() as controller:
        controller.set(parameter, channel, value)
        cmd_key = parameter.name.lower()
        cmd_type = "set"  # Irrelevant as it's not apart of the address.
        assert controller.instrument_lib.message == controller._build_message(cmd_key, cmd_type, channel, value)
