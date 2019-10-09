import copy
import os
import functools

import astropy.units
import numpy as np
from poppy.dms import ContinuousDeformableMirror
import pytest

from catkit.hardware.boston.DmCommand import DmCommand
from catkit.emulators.boston_dm import PoppyBostonDMController

data_dir = os.path.join(os.path.dirname(__file__), "data")
# Example specs mimic Boston Kilo 952 DM


class TestPoppyBostonDMController:
    number_of_actuators = 952
    command_length = 2048

    poppy_dm1 = ContinuousDeformableMirror(name='Boston DM1',
                                           dm_shape=(34, 34),
                                           radius=12 / 2,
                                           influence_func=os.path.join(data_dir, "dm_influence_function_dm5v2.fits"),
                                           actuator_spacing=300 * astropy.units.micron,
                                           include_actuator_print_through=True,
                                           actuator_print_through_file=os.path.join(data_dir, "boston_mems_actuator_medres.fits"),
                                           actuator_mask_file=os.path.join(data_dir, "boston_kilodm-952_mask.fits"),
                                           inclination_y=10)

    poppy_dm2 = copy.deepcopy(poppy_dm1)
    poppy_dm2.shift_x = -0.00015 * astropy.units.m
    poppy_dm2.shift_y = 0.0
    poppy_dm2.flip_x = True

    instantiate_dm_controller = functools.partial(PoppyBostonDMController, "boston_kilo952",
                                                  number_of_actuators,
                                                  command_length,
                                                  poppy_dm1,
                                                  dm2=poppy_dm2)

    def test_with(self):
        flat_dm1 = DmCommand(np.zeros(self.number_of_actuators), 1)
        flat_dm2 = DmCommand(np.zeros(self.number_of_actuators), 2)
        with self.instantiate_dm_controller() as dm:
            dm.apply_shape_to_both(flat_dm1, flat_dm2)

        assert dm.instrument is None

    def test_subsequent_with(self):
        flat_dm1 = DmCommand(np.zeros(self.number_of_actuators), 1)
        flat_dm2 = DmCommand(np.zeros(self.number_of_actuators), 2)
        with self.instantiate_dm_controller() as dm:
            dm.apply_shape_to_both(flat_dm1, flat_dm2)

        assert dm.instrument is None

        assert dm
        with dm:
            dm.apply_shape_to_both(flat_dm1, flat_dm2)

        assert dm.instrument is None

    def test_access_after_with(self):
        flat_dm1 = DmCommand(np.zeros(self.number_of_actuators), 1)
        flat_dm2 = DmCommand(np.zeros(self.number_of_actuators), 2)
        with self.instantiate_dm_controller() as dm:
            dm.apply_shape_to_both(flat_dm1, flat_dm2)

        with pytest.raises(AttributeError):
            dm.apply_shape_to_both(flat_dm1, flat_dm2)

    def test_access_outside_with(self):
        flat_dm1 = DmCommand(np.zeros(self.number_of_actuators), 1)
        flat_dm2 = DmCommand(np.zeros(self.number_of_actuators), 2)
        dm = self.instantiate_dm_controller()
        with pytest.raises(AttributeError):
            dm.apply_shape_to_both(flat_dm1, flat_dm2)

    def test_keep_alive(self):
        flat_dm1 = DmCommand(np.zeros(self.number_of_actuators), 1)
        flat_dm2 = DmCommand(np.zeros(self.number_of_actuators), 2)
        with self.instantiate_dm_controller() as dm:
            dm._Instrument__keep_alive = True

        dm.apply_shape_to_both(flat_dm1, flat_dm2)
        dm._Instrument__close()
        assert dm.instrument is None
        assert not dm._Instrument__keep_alive

    def test_del(self):
        # This is implicitly tested in all other tests, but hey.
        with self.instantiate_dm_controller() as dm:
            dm._Instrument__keep_alive = True
        del dm
