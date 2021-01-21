import os
import requests

from astropy.io import fits
import h5py

from catkit.hardware.FourDTechnology.Accufiz import Accufiz
from catkit.interfaces.Instrument import SimInstrument


class PoppyAccufizEmulator:

    def __init__(self, optics, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data = None
        self.optics = optics

    def get(self, url, params=None, **kwargs):
        resp = requests.Response()
        resp.text = "success"
        return resp

    def post(self, url, data=None, json=None, **kwargs):
        raise NotImplementedError("TODO: See CATKIT-66.")

        command = os.path.basename(url)

        if command == "AverageMeasure":
            #self.data = optics.do_stuff()
        elif command == "SaveMeasurement":
            filepath = data["fileName"]
            if self.data is None:
                raise RuntimeError(f"No data taken to save.")
            #h5py.write(self.data, f"{filepath}.h5")
        else:
            raise NotImplementedError(f"The command '{command}' is not implemented.")


class Accufiz(Accufiz, SimInstrument):
    instrument_lib = PoppyAccufizEmulator
