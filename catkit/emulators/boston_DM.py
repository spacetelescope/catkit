import copy

import astropy.units

from catkit.hardware.boston.DmCommand import DmCommand
from catkit.hardware.boston.BostonDmController import BostonDmController
import hicat.util


class PoppyBmcEmulator:

    NO_ERR = 0

    def __init__(self, num_actuators, command_length, dm1, dm2=None):
        self._num_actuators = num_actuators
        self._command_length = command_length
        self.dm1 = dm1
        self.dm2 = dm2

    def BmcDm(self):
        return self

    def open_dm(self, serial_number):
        return self.NO_ERR

    def close_dm(self):
        return self.NO_ERR

    def send_data(self, full_dm_command):

        meters = astropy.units.m

        if self.dm1:
            dm1_command = full_dm_command[:self._num_actuators]
            dm1_image = hicat.util.convert_dm_command_to_image(dm1_command)
            self.dm1.set_surface(dm1_image * meters)
        if self.dm2:
            dm2_command = full_dm_command[self._command_length // 2:self._command_length // 2 + self._num_actuators]
            dm2_image = hicat.util.convert_dm_command_to_image(dm2_command)
            self.dm2.set_surface(dm2_image * meters)

        return self.NO_ERR

    def num_actuators(self):
        # Oddly, the hardware actually returns the command length, not the number of actuators per dm etc.
        return self._command_length

    def error_string(self, status):
        return "Woops!"


class PoppyDMCommand(DmCommand):
    def __init__(self, dm_command_object):
        """Copy constructor."""
        vars(self).update(copy.deepcopy(vars(dm_command_object)))

    def to_dm_command(self, calibrate=False):
        return super().to_dm_command(calibrate=calibrate)


class PoppyBostonDMController(BostonDmController):

    instrument_lib = PoppyBmcEmulator

    def __init__(self, config_id, num_actuators, command_length, dm1, dm2=None):
        self.instrument_lib = self.instrument_lib(num_actuators, command_length, dm1, dm2)
        return super().__init__(config_id)

    def apply_shape_to_both(self, dm1_command_object, dm2_command_object):
        if dm1_command_object.as_volts or dm2_command_object.as_volts:
            raise NotImplementedError("Simulator needs to convert DM command from volts to nm")

        _dm1_command_object = PoppyDMCommand(dm1_command_object)
        _dm2_command_object = PoppyDMCommand(dm2_command_object)
        return super().apply_shape_to_both(_dm1_command_object, _dm2_command_object)

    def apply_shape(self, dm_command_object, dm_num):
        if dm_command_object.as_volts:
            raise NotImplementedError("Simulator needs to convert DM command from volts to nm")

        _dm_command_object = PoppyDMCommand(dm_command_object)
        return super().apply_shape(_dm_command_object, dm_num)
