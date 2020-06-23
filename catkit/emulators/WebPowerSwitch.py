import requests

from catkit.interfaces.Instrument import SimInstrument
import catkit.hardware.WebPowerSwitch


class WebPowerSwitchRequestsEmulator():

    def __init__(self, status_code=200):
        self.status_code = status_code

    def get(self, url, params=None, **kwargs):
        resp = requests.Response()
        resp.status_code = self.status_code
        return resp


class WebPowerSwitch(SimInstrument, catkit.hardware.WebPowerSwitch.WebPowerSwitch):
    instrument_lib = WebPowerSwitchRequestsEmulator
