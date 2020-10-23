import logging

import astropy.units as u
import poppy.dms

from catkit.hardware import testbed_state
from catkit.hardware.iris_ao.IrisAoDmController import IrisAoDmController
from catkit.hardware.iris_ao import util
from catkit.interfaces.Instrument import SimInstrument


class PoppyIrisAO(poppy.dms.HexSegmentedDeformableMirror):
    """
    Adding attributes to describe a typical IrisAO deformable mirror.
    TODO: drop this one into hicat_sim.py
    """
    def __init__(self, **super_kwargs):

        # TODO: do the thing where we use the negative flatmap to simulate the non-flattened DM surface?

        super().__init__(**super_kwargs)


class FakeStdin:
    """Because maybe this will work"""
    def __init__(self, iris_dm, config_id, filename_ptt_dm):
        self.iris_dm = iris_dm
        self.config_id = config_id
        self.filename_ptt_dm = filename_ptt_dm

        self.stdin = FakeWriteAndFlush(iris_dm, config_id, filename_ptt_dm)


class FakeWriteAndFlush:

    def __init__(self, iris_dm, config_id, filename_ptt_dm):
        self.iris_dm = iris_dm
        self.config_id = config_id
        self.filename_ptt_dm = filename_ptt_dm

    def write(self, string):
        """
        There are two options:
        b'config\n': which applies a command to the IrisAO
        b'quit\n': closes the connection to the IrisAO
        """

        if string == b'config\n':
            # Read ConfigPTT.ini
            number_of_segments = util.iris_num_segments(self.config_id)
            data = util.read_ini(self.filename_ptt_dm, number_of_segments)   # returns a dict, the command to be sent to the DM

            # Put it on the iris_dm
            # Setting the simulated IrisAO means setting each actuator individually
            for seg, values in data.items():
                self.iris_dm.set_actuator(seg-1, values[0]*u.um, values[1]*u.mrad, values[2]*u.mrad)   #TODO: double-check the -1 here, meant to correct for different segment names

        elif string == b'quit\n':
            # When we're done, leave the simulated DMs in a flat state, to avoid persistent
            # state between different simulation calls.
            # This intentionally differs from hardware behavior in which an unpowered DM is non-flat.
            self.iris_dm.flatten()
            testbed_state.iris_command_object = None

    def flush(self):
        """ This doesn't need to do anything when in simulation, as it is always called together
        with write(), but we need to have it."""
        pass


class PoppyIrisaoEmulator:

    def __init__(self, iris_dm, config_id, filename_ptt_dm):
        self.log = logging.getLogger(f"{self.__module__}.{self.__class__.__qualname__}")
        self.iris_dm = iris_dm
        self.config_id = config_id
        self.filename_ptt_dm = filename_ptt_dm

    def Popen(self, cmd, stdin, stdout, stderr, cwd, bufsize, creationflags):
        """ Something something, open a connection?"""
        self.instrument = FakeStdin(self.iris_dm, self.config_id, self.filename_ptt_dm)
        return self.instrument


class PoppyIrisAOController(SimInstrument, IrisAoDmController):

    instrument_lib = PoppyIrisaoEmulator