import logging

import astropy.units as u
import poppy.dms

from catkit.hardware import testbed_state
from catkit.hardware.iris_ao.IrisAoDmController import IrisAoDmController
from catkit.hardware.iris_ao import util
from catkit.interfaces.Instrument import SimInstrument


class PoppyIrisAO(poppy.dms.HexSegmentedDeformableMirror):
    def __init__(self, **super_kwargs):

        # TODO: do the thing where we use the negative flatmap to simulate the non-flattened DM surface

        super().__init__(**super_kwargs)


class FakeStdin:
    """Because maybe this will work"""
    def __init__(self):
        self.stdin = FakeWriteAndFlush()


class FakeWriteAndFlush:
    def write(self, string):
        pass

    def flush(self):
        pass


class PoppyIrisaoEmulator:

    def __init__(self, iris_dm):
        self.log = logging.getLogger(f"{self.__module__}.{self.__class__.__qualname__}")
        self.iris_dm = iris_dm
        self.command = None

    def Popen(self, cmd, stdin, stdout, stderr, cwd, bufsize, creationflags):
        """ Something something, open a connection?"""
        self.instrument = FakeStdin()
        return self.instrument

    def send_data(self, data):
        """
        Setting the simulated IrisAO means setting each actuator individually

        :param data: dict, the command to be sent to the DM
        """
        for seg, values in data.items():
            self.iris_dm.set_actuator(seg, values[0]*u.um, values[1]*u.mrad, values[2]*u.mrad)

    def zero(self, return_zeros=False):
        """Put zeros on the DM. This does not correspond to a flattened DM.

        :return: If return_zeros=True, return a dictionary of zeros
        """
        zero_list = util.create_zero_list(util.iris_num_segments(self.config_id))
        zeros = util.create_dict_from_list(zero_list, util.iris_pupil_naming(self.config_id))
        self.send_data(zeros)

        # Update the testbed state
        self._update_iris_state(zeros)

        if return_zeros:
            return zeros

    def _close(self):
        """ Close connection to (simulated) DM hardware """
        # When we're done, leave the simulated DMs in a flat state, to avoid persistent
        # state between different simulation calls.
        # This intentionally differs from hardware behavior in which an unpowered DM is non-flat.
        self.iris_dm.flatten()
        self._close_iris_controller_testbed_state()

    def apply_shape(self, dm_shape, dm_num=1):
        """
        Apply a command object to the Iris AO after adding the flatmap from the configfile.
        The units of said SegmentedDmCommand object are mrad for tip/tilt, um for piston.

        :param dm_shape: instance of SegmentedDmCommand class
        :param dm_num: int, this must always be 1 since only one DM can be controlled
                       with this controller.
        """
        if dm_num != 1:
            raise NotImplementedError("You can only control one Iris AO at a time")

        # Use DmCommand class to format the single command correctly.
        command = dm_shape.to_command()

        # Send array to DM.
        self.send_data(command)

        # Update the dm_command class attribute.
        self.command = command

        # Update the testbed_state.
        self._update_iris_state(dm_shape)

    def apply_shape_to_both(self, dm1_shape=None, dm2_shape=None):
        """Method only used by the BostonDmController"""
        raise NotImplementedError("apply_shape_to_both is not implemented for the Iris AO")

    @staticmethod
    def _update_iris_state(command_object):
        testbed_state.iris_command_object = command_object

    @staticmethod
    def _close_iris_controller_testbed_state():
        testbed_state.iris_command_object = None


class PoppyIrisAOController(SimInstrument, IrisAoDmController):

    instrument_lib = PoppyIrisaoEmulator