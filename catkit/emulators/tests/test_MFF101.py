import pytest

from catkit.catkit_types import FlipMountPosition


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


def test_position_tracking():
    from catkit.emulators.thorlabs.MFF101 import MFF101Emulator
    from catkit.interfaces.Instrument import SimInstrument
    import catkit.hardware.thorlabs.ThorlabsMFF101

    class HicatMFF101Emulator(MFF101Emulator):
        def __init__(self,  config_id, in_beam_position):
            super().__init__(config_id, in_beam_position)
            self.pos1_counter = 0
            self.pos2_counter = 0

        def move_to_position_1(self):
            self.pos1_counter += 1

        def move_to_position_2(self):
            self.pos2_counter += 1

    class ThorlabsMFF101(SimInstrument, catkit.hardware.thorlabs.ThorlabsMFF101.ThorlabsMFF101):
        instrument_lib = HicatMFF101Emulator

    with ThorlabsMFF101(config_id="dummy", serial="sn", in_beam_position=1) as device:
        device.move(FlipMountPosition.IN_BEAM)
        assert device.current_position is FlipMountPosition.IN_BEAM
        assert device.instrument_lib.pos1_counter == 1

        device.move(FlipMountPosition.OUT_OF_BEAM)
        assert device.current_position is FlipMountPosition.OUT_OF_BEAM
        assert device.instrument_lib.pos2_counter == 1

        device.move(FlipMountPosition.OUT_OF_BEAM)
        assert device.current_position is FlipMountPosition.OUT_OF_BEAM
        assert device.instrument_lib.pos2_counter == 1  # Already in position so shouldn't be incremented.

        device.move(FlipMountPosition.OUT_OF_BEAM, force=True)
        assert device.current_position is FlipMountPosition.OUT_OF_BEAM
        assert device.instrument_lib.pos2_counter == 2
