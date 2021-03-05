import numpy as np

from catkit.emulators.thorlabs.MCLS1 import MCLS1


def test_get_cuurent():
    current = 50
    with MCLS1(config_id="dummy", device_id="dummy", channel=1, nominal_current=current) as laser:
        assert laser.instrument_lib.current[0] == current
        assert laser.get_current() == current


def test_set_current():
    with MCLS1(config_id="dummy", device_id="dummy", channel=1, nominal_current=50) as laser:
        new_channel = 3
        new_current = 100
        assert laser.get_current() == 50
        laser.set_current(value=new_current, channel=new_channel)
        assert laser.instrument_lib.active_channel == new_channel
        assert laser.instrument_lib.current[new_channel-1] == new_current
        assert laser.get_active_channel() == new_channel
        assert laser.get_current(channel=new_channel) == new_current


def test_system_enable():
    laser = MCLS1(config_id="dummy", device_id="dummy", channel=1, nominal_current=50)
    assert not laser.instrument_lib.system_enabled
    with laser as laser:
        assert laser.instrument_lib.system_enabled
        laser.set_system_enable(False)
        assert not laser.instrument_lib.system_enabled


def test_channel_enable():
    channel = 1
    laser = MCLS1(config_id="dummy", device_id="dummy", channel=channel, nominal_current=50)
    assert not np.any(laser.instrument_lib.channel_enabled)
    with laser as laser:
        assert laser.instrument_lib.channel_enabled[channel-1]
        laser.set_channel_enable(channel, False)
        assert not np.any(laser.instrument_lib.channel_enabled)

        laser.set_channel_enable(3, True)
        assert laser.instrument_lib.channel_enabled[3-1]
        laser.set_channel_enable(3, False)
        assert not np.any(laser.instrument_lib.channel_enabled)
