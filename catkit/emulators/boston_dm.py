import copy
import logging

import hicat.util
import numpy as np

import poppy.dms

import catkit.hardware.boston.DmCommand
from catkit.hardware.boston.BostonDmController import BostonDmController
from catkit.interfaces.Instrument import SimInstrument


class PoppyBmcEmulator:
    """ This class (partially) emulates the Boston Micromachines Company's (BMC)
    SDK that communicates with their kilo 952 deformable mirror (DM) controller.
    It is not yet functionally complete."""

    NO_ERR = 0
    dac_bit_width = 14
    max_volts = 200  # TODO: make dynamic

    def __init__(self, num_actuators, command_length, dm1, dm2=None):
        self.log = logging.getLogger(f"{self.__module__}.{self.__class__.__qualname__}")
        self._num_actuators = num_actuators
        self._command_length = command_length
        self.dm1 = dm1
        self.dm2 = dm2

        # As the class name suggests, the design only works with ``poppy.dms.ContinuousDeformableMirror``.
        assert isinstance(dm1, poppy.dms.ContinuousDeformableMirror)
        assert isinstance(dm2, poppy.dms.ContinuousDeformableMirror)

    def BmcDm(self):
        return self

    def open_dm(self, _serial_number):
        return self.NO_ERR

    def close_dm(self):
        return self.NO_ERR

    def send_data(self, full_dm_command):

        assert np.min(full_dm_command) >= 0 and np.max(full_dm_command) <= 1, \
            "DM command must be unitless (normalized Volts), i.e. 0.0-1.0."

        full_dm_command = copy.deepcopy(full_dm_command)

        if self.dac_bit_width:
            self.log.info(f"Simulating DM quantization with {self.dac_bit_width}b DAC")

            quantization_step_size = 1.0/(2**self.dac_bit_width - 1)
            full_dm_command.data = quantization_step_size * np.round(full_dm_command / quantization_step_size)

        # Convert to Volts.
        full_dm_command = full_dm_command * self.max_volts

        if self.dm1:
            dm1_command = full_dm_command[:self._num_actuators]
            dm1_image = hicat.util.convert_dm_command_to_image(dm1_command)
            # Convert to meters
            dm1_image = catkit.hardware.boston.DmCommand.convert_volts_to_m(dm1_image)
            self.dm1.set_surface(dm1_image)
        if self.dm2:
            dm2_command = full_dm_command[self._command_length // 2:self._command_length // 2 + self._num_actuators]
            dm2_image = hicat.util.convert_dm_command_to_image(dm2_command)
            # Convert to meters
            dm2_image = catkit.hardware.boston.DmCommand.convert_volts_to_m(dm2_image)
            self.dm2.set_surface(dm2_image)

        return self.NO_ERR

    def num_actuators(self):
        # Oddly, the hardware actually returns the command length, not the number of actuators per dm etc.
        return self._command_length

    def error_string(self, _status):
        return "Woops!"


class PoppyBostonDMController(SimInstrument, BostonDmController):
    """ Emulated version of the real hardware `BostonDmController` class.
    This directly follows the hardware control except that the communication layer to the
    hardware uses our emulated version of Boston's DM SDK - `PoppyBmcEmulator`"""

    instrument_lib = PoppyBmcEmulator
