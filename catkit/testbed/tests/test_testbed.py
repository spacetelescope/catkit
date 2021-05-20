import pytest

from catkit.emulators.npoint_tiptilt import SimNPointLC400
import catkit.testbed


@catkit.testbed.devices.link(key="npoint_a", aliases=["lc400_a", "lc400_A"])
def npoint_a():
    return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy")


@catkit.testbed.devices.link(key="npoint_b", aliases=["lc400_B"])
def npoint_b():
    return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy")


def test_device_cache_collision(derestricted_device_cache):
    with npoint_a() as device_a:
        devices = {"npoint_a": device_a}

        # Cache devices in catkit.testbed.devices.
        catkit.testbed.devices.update(devices)

        new_devices = {"npoint_a": device_a}
        catkit.testbed.devices.update(new_devices)

        with npoint_b() as device_b:
            new_devices = {"npoint_a": device_b}
            with pytest.raises(KeyError):
                catkit.testbed.devices.update(new_devices)

    catkit.testbed.devices.clear()
    assert not catkit.testbed.devices


def test_cache_copy(derestricted_device_cache):
    with npoint_a() as device_a:
        devices = {"npoint_a": device_a}

        # Cache devices in catkit.testbed.devices.
        catkit.testbed.devices.update(devices)

    with pytest.raises(NotImplementedError):
        devices = catkit.testbed.devices.copy()


def test_access_equality(derestricted_device_cache):
    assert catkit.testbed.devices["npoint_a"] is npoint_a()


def test_access_inequality(derestricted_device_cache):
    assert npoint_a() is not catkit.testbed.devices["npoint_a"]


def test_aliases(derestricted_device_cache):
    assert "npoint_a" in catkit.testbed.devices.callbacks
    assert "lc400_a" in catkit.testbed.devices.callbacks
    assert "lc400_A" in catkit.testbed.devices.callbacks

    assert "lc400_A" not in catkit.testbed.devices.aliases

    device = npoint_a()
    assert "lc400_a" not in catkit.testbed.devices.aliases

    device = catkit.testbed.devices["npoint_a"]
    assert "lc400_a" in catkit.testbed.devices.aliases
    assert "lc400_A" in catkit.testbed.devices.aliases
    assert device is catkit.testbed.devices["npoint_a"]
    assert device is catkit.testbed.devices["lc400_a"]
    assert device is catkit.testbed.devices["lc400_A"]


def test_aliases_2(derestricted_device_cache):
    assert catkit.testbed.devices["lc400_B"] is npoint_b()


def test_with_stmnt(derestricted_device_cache):
    device_a = catkit.testbed.devices["npoint_a"]
    assert device_a.instrument
    with npoint_a() as npoint_a2:
        assert device_a is npoint_a2
        assert device_a.instrument
    assert device_a.instrument
    assert device_a is catkit.testbed.devices["npoint_a"]
    assert device_a is npoint_a()
    del catkit.testbed.devices["npoint_a"]
    assert not device_a.is_open()  # Connection was closed.


def test_with_stmnt_2(derestricted_device_cache):
    with npoint_a() as device_a:
        assert device_a.instrument
        assert device_a is not catkit.testbed.devices["npoint_a"]
    assert device_a is not catkit.testbed.devices["npoint_a"]
    assert device_a is not npoint_a()
    assert not device_a.instrument


def test_nested_with_stmnts(derestricted_device_cache):
    with npoint_a() as device_a:
        assert device_a.instrument
        with device_a as dev_a:
            assert device_a is dev_a
        assert device_a.instrument, "Inner with stmnt closed the device when it shouldn't have."
    assert not device_a.instrument, "Outer with stmnt didn't close the device when it should have."


def test_pop(derestricted_device_cache):
    device_a = catkit.testbed.devices["npoint_a"]
    assert device_a.instrument
    catkit.testbed.devices.pop("npoint_a")
    assert not device_a.instrument


def test_clear(derestricted_device_cache):
    device_a = catkit.testbed.devices["npoint_a"]
    assert device_a.instrument
    catkit.testbed.devices.clear()
    assert not device_a.instrument


def test_restriction():
    with pytest.raises(NameError):
        catkit.testbed.devices["npoint_a"]


def test_DeviceCache():
    class Dev(catkit.testbed.DeviceCacheEnum):
        NPOINT_C = ("npoint a for test", "dummy_config_id")

    @catkit.testbed.devices.link(key=Dev.NPOINT_C)
    def npoint_c():
        return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy")

    with catkit.testbed.devices:
        device_c = Dev.NPOINT_C
        assert device_c.instrument


def test_mutable_enum():
    class Dev(catkit.testbed.DeviceCacheEnum):
        NPOINT_C = ("npoint a for test", "dummy_config_id")

    @catkit.testbed.devices.link(key=Dev.NPOINT_C)
    def npoint_c():
        return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy")

    with catkit.testbed.devices as devices:
        assert Dev.NPOINT_C.instrument
        Dev.NPOINT_C.test_attr = "hahahah"
        assert devices[Dev.NPOINT_C].test_attr == "hahahah"


def test_immutable_enum():
    class Dev(catkit.testbed.ImmutableDeviceCacheEnum):
        NPOINT_C = ("npoint a for test", "dummy_config_id")

    @catkit.testbed.devices.link(key=Dev.NPOINT_C)
    def npoint_c():
        return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy")

    with catkit.testbed.devices:
        assert Dev.NPOINT_C.instrument
        with pytest.raises(AttributeError):
            Dev.NPOINT_C.instrument = "hahahah"


def test_enum_is_open():
    class Dev(catkit.testbed.DeviceCacheEnum):
        NPOINT_C = ("npoint a for test", "dummy_config_id")

    @catkit.testbed.devices.link(key=Dev.NPOINT_C)
    def npoint_c():
        return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy")

    with catkit.testbed.devices:
        assert not Dev.NPOINT_C.is_open()
        assert not Dev.NPOINT_C.is_open(), "is_open() isn't free of side-effects."
        Dev.NPOINT_C()
        assert Dev.NPOINT_C.is_open()
