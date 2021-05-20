import copy
import logging

import numpy as np

import poppy.dms

import catkit.util
import catkit.hardware.boston.DmCommand
from catkit.hardware.boston.BostonDmController import BostonDmController
from catkit.interfaces.Instrument import SimInstrument
from catkit.multiprocessing import MutexedNamespace


class PoppyBostonDM(MutexedNamespace, poppy.dms.ContinuousDeformableMirror):
    """
    Wraps `poppy.dms.ContinuousDeformableMirror` so as to encapsulate the additional DM
    attributes required to describe a typical Boston Micromachines DM.

    :param max_volts: int
        The maximum voltage limit as defined in the DM profile file.
    :param meter_per_volt_map: array-like
        Calibration data array map for converting each actuator voltage to surface height in meters.
    :param flat_map_voltage: array-like
        Calibration data array describing the flat map characteristics of the DM. Has units volts.
    :param flat_map_bias_voltage: float, int
        Voltage bias/offset already applied to `flat_map`. Subtracted from `flat_map` to create an unbiased flat map.
    :param super_kwargs:
        Keyword args that get passed to  `poppy.dms.ContinuousDeformableMirror()`
    """

    def __init__(self, max_volts, meter_per_volt_map, flat_map_voltage=None, flat_map_bias_voltage=None, **super_kwargs):

        self.max_volts = max_volts
        self.meter_per_volt_map = meter_per_volt_map
        self.flat_map_voltage = flat_map_voltage
        self.flat_map_bias_voltage = flat_map_bias_voltage

        # TODO: HICAT-652 - unbiasing the flatmap should obtain ``bias_voltage`` from the flatmap file meta.
        self.unbiased_flatmap_voltage = self.flat_map_voltage.copy()
        if self.flat_map_bias_voltage is not None:
            self.unbiased_flatmap_voltage -= self.flat_map_bias_voltage

        super().__init__(**super_kwargs)


class PoppyBmcEmulator:
    """ This class (partially) emulates the Boston Micromachines Company's (BMC)
    SDK that communicates with their kilo 952 deformable mirror (DM) controller.
    It is not yet functionally complete.
    See `catkit.hardware.boston.sdk.python3.v3_5_1.bmc` for completeness."""

    NO_ERR = 0

    def __init__(self, num_actuators, command_length, dac_bit_width, dm1, dm2=None):
        self.log = logging.getLogger()
        self._num_actuators = num_actuators
        self._command_length = command_length
        self._dac_bit_width = dac_bit_width
        self.dm1 = dm1
        self.dm2 = dm2

        # As the class name suggests, the design only works with ``poppy.dms.ContinuousDeformableMirror``.
        # assert isinstance(dm1, (PoppyBostonDM, PoppyBostonDM.Proxy)), type(dm1)
        # if dm2 is not None:
        #     assert isinstance(dm2, (PoppyBostonDM, PoppyBostonDM.Proxy))

    def BmcDm(self):
        return self

    def open_dm(self, _serial_number):
        return self.NO_ERR

    def close_dm(self):
        """ Close connection to (simulated) DM hardware """
        # When we're done, leave the simulated DMs in a flat state, to avoid persistent
        # state between different simulation calls.
        # This intentionally differs from hardware behavior in which an unpowered DM is non-flat.
        # See https://github.com/spacetelescope/catkit/63
        self.dm1.flatten()
        if self.dm2 is not None:
            self.dm2.flatten()
        return self.NO_ERR

    def send_data(self, full_dm_command):
        """
        Emulate the sending of data to the Boston DM driver/controller
        by "sending" the command data to Poppy DMs.

        The real hardware call receives `full_dm_command` as a unitless float array.
        It would then convert it to Volts as `full_dm_command * max_volts`,
        where for the Boston twin Kilo driver's `max_volts` := 200V.
        This function needs to convert the command to meters to be applied to the Poppy DM simulator.

        Has the following features:

         * Clips the command to 0.0 and 1.0 just as the hardware does.
         * Simulates DAC voltage quantization.
         * Simulates the 0V "off" relaxed surface state using each DMs (unbiased) flat map.
         * Converts the command to volts using max_volts
         * Converts volts to meters using each DMs `meter_per_volt_map`.

        :param full_dm_command: float array-like
            Array of floats of length self._command_length.
            Values should be in the range 0.0 to 1.0 and are clipped otherwise.
        :return: int
            Error status: self.NO_ERR := 0, raises otherwise.
        """

        full_dm_command = copy.deepcopy(full_dm_command)

        # Clip command between 0.0 and 1.0 just as the hardware does.
        np.clip(full_dm_command, a_min=0, a_max=1, out=full_dm_command)

        if self._dac_bit_width:
            self.log.info(f"Simulating DM quantization with {self._dac_bit_width}b DAC")

            quantization_step_size = 1.0/(2**self._dac_bit_width - 1)
            full_dm_command = quantization_step_size * np.round(full_dm_command / quantization_step_size)

        def convert_command_to_poppy_surface(dm_command, dm):
            # Convert to volts
            dm_command *= dm.max_volts

            # Convert to 2D image
            dm_image = catkit.hardware.boston.DmCommand.convert_dm_command_to_image(dm_command)

            # The 0 Volt DM surface is not flat. Attempt to simulate this.
            if dm.unbiased_flatmap_voltage is not None:
                dm_image -= dm.flat_map_voltage

            # Convert to meters
            dm_surface = catkit.hardware.boston.DmCommand.convert_volts_to_m(dm_image, None, dm.meter_per_volt_map)

            return dm_surface

        if self.dm1:
            dm1_command = full_dm_command[:self._num_actuators]
            self.dm1.set_surface(convert_command_to_poppy_surface(dm1_command, self.dm1))
        if self.dm2:
            dm2_command = full_dm_command[self._command_length // 2:self._command_length // 2 + self._num_actuators]
            self.dm2.set_surface(convert_command_to_poppy_surface(dm2_command, self.dm2))

        return self.NO_ERR

    def num_actuators(self):
        # Oddly, the hardware actually returns the command length, not the number of actuators per dm etc.
        return self._command_length

    def error_string(self, _status):
        return f"An emulated error occurred with the following status code: {_status}!"


class PoppyBostonDMController(SimInstrument, BostonDmController):
    """ Emulated version of the real hardware `BostonDmController` class.
    This directly follows the hardware control except that the communication layer to the
    hardware uses our emulated version of Boston's DM SDK - `PoppyBmcEmulator`"""

    instrument_lib = PoppyBmcEmulator
