import pytest


def test_import():
    import catkit.hardware.thorlabs.ThorlabsMFF101


def test_delayed_import():
    import catkit.hardware.thorlabs.ThorlabsMFF101

    with pytest.raises(ImportError):
        catkit.hardware.thorlabs.ThorlabsMFF101.ThorlabsMFF101()


def test_emulator_import():
    from catkit.emulators.thorlabs.MFF101 import MFF101Emulator
    from catkit.interfaces.Instrument import SimInstrument
    import catkit.hardware.thorlabs.ThorlabsMFF101

    class HicatMFF101Emulator(MFF101Emulator):
        def move_to_position_1(self):
            pass

        def move_to_position_2(self):
            pass

    class ThorlabsMFF101(SimInstrument, catkit.hardware.thorlabs.ThorlabsMFF101.ThorlabsMFF101):
        instrument_lib = HicatMFF101Emulator

    ThorlabsMFF101(config_id="dummy", serial="sn", in_beam_position=1)
