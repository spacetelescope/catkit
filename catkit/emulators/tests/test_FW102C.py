import itertools

import pytest

from catkit.catkit_types import ColorWheelFilter
from catkit.emulators.thorlabs.FW102C import FW102CEmulator
from catkit.hardware.thorlabs.ThorlabsFW102C import ThorlabsFW102C
from catkit.interfaces.Instrument import SimInstrument


class SimColorFW102C(SimInstrument, ThorlabsFW102C):
    class DummyEmulator(FW102CEmulator):
        def move_filter(self, position):
            pass

    instrument_lib = DummyEmulator


class Filter(ColorWheelFilter):
    nm600 = ("600nm", 600, 1)
    nm610 = ("610nm", 610, 2)
    nm640 = ("640nm", 640, 3)


ALL_FILTER_KINDS = list(itertools.chain(*[(f, f.filter_name, f.wavelength, f.position) for f in Filter]))


def test_initial_state():
    with SimColorFW102C(config_id="config_id", visa_id="dummy_id", filter_type=Filter) as wheel:
        assert wheel.current_position == 1
        assert wheel.current_filter is Filter(1)

        assert wheel.get_position() == 1
        assert wheel.get_filter() is Filter(1)

        assert wheel.current_filter.position == wheel.current_position


@pytest.mark.parametrize("filter", ALL_FILTER_KINDS)
def test_state(filter):
    with SimColorFW102C(config_id="config_id", visa_id="dummy_id", filter_type=Filter) as wheel:
        wheel.set_position(filter)
        assert wheel.current_filter is Filter(filter)
        assert wheel.get_filter() is Filter(filter)
        assert wheel.current_position == Filter(filter).position


@pytest.mark.parametrize("filter", ALL_FILTER_KINDS)
def test_move(filter):
    with SimColorFW102C(config_id="config_id", visa_id="dummy_id", filter_type=Filter) as wheel:
        wheel.move(filter)
        assert wheel.current_filter is Filter(filter)
        assert wheel.get_filter() is Filter(filter)
        assert wheel.current_position == Filter(filter).position
