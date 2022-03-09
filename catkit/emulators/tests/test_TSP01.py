from catkit.emulators.thorlabs.TSP01 import TSP01Emulator
import catkit.hardware.thorlabs.ThorlabsTSP01
from catkit.interfaces.Instrument import SimInstrument


class TSP01RevB(SimInstrument, catkit.hardware.thorlabs.ThorlabsTSP01.TSP01RevB):
    instrument_lib = TSP01Emulator


def test_temp_humidity():
    set_temp = 25.7
    set_humidity = 11.2
    with TSP01RevB(config_id="dummy", serial_number="12345", temp=set_temp, humidity=set_humidity) as device:
        temp, humidity = device.get_temp_humidity()
        assert temp == set_temp
        assert humidity == set_humidity
