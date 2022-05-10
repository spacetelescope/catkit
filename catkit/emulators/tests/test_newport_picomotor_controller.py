from catkit.emulators.newport.NewportPicomotorController import NewportPicoMotorControllerEmulator
from catkit.hardware.newport.NewportPicomotorController import NewportPicomotorController
from catkit.interfaces.Instrument import SimInstrument


class SimNewportPicomotorController(SimInstrument, NewportPicomotorController):
    instrument_lib = NewportPicoMotorControllerEmulator


def test_relative_move():
    with SimNewportPicomotorController(config_id="dummy", home_position=[0]*SimNewportPicomotorController.N_AXIS) as device:
        for axis in range(1, device.N_AXIS+1):
            assert device.get_position(axis) == 0
            device.reset()