from catkit.interfaces.Instrument import SimInstrument
import catkit.hardware.WebPowerSwitch


class WebPowerSwitchRequestsEmulator:
    def get(self, url, params=None, **kwargs):
        pass


class WebPowerSwitch(SimInstrument, catkit.hardware.WebPowerSwitch.WebPowerSwitch):
    instrument_lib = WebPowerSwitchRequestsEmulator
