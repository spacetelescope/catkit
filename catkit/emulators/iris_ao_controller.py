import os

import astropy.units as u
import numpy as np
import poppy

from catkit.hardware.iris_ao.iris_ao_controller import IrisAoDmController
import catkit.hardware.iris_ao.segmented_dm_command as segmented_dm_command
import catkit.hardware.iris_ao.util
from catkit.interfaces.Instrument import SimInstrument
import catkit.util
from catkit.multiprocessing import MutexedNamespace
from packaging.version import Version


class PoppyIrisAODM(MutexedNamespace, poppy.dms.HexSegmentedDeformableMirror):

    @property
    def number_of_segments(self):
        return self.dm_shape

    def __init__(self, mcf_filename, custom_flat_filename, mirror_serial, **super_kwargs):
        super().__init__(**super_kwargs)

        self.mirror_serial = mirror_serial

        # Read the manufacturers .mcf "flat" file.
        # This is implicitly applied by the driver/controller and is NOT a present contribution of the command sent to
        # the driver/controller by catkit.hardware.iris_ao.iris_ao_controller.IrisAoDmController.
        self.mcf_filename = mcf_filename
        #mcf_data, self.mirror_serial = catkit.hardware.iris_ao.util.read_mcf(self.mcf_filename, self.number_of_segments)

        self.custom_flat_filename = custom_flat_filename
        custom_flat_data = catkit.hardware.iris_ao.util.read_ini(self.custom_flat_filename, self.number_of_segments)   # this returns a DM command dict

        # A flat Poppy surfaces := 0.
        self.relaxed_poppy_surface = self.invert_data(custom_flat_data)  # + mcf_data
        self.relax()  # ??? See https://github.com/spacetelescope/catkit/issues/63 (we don't currently relax the bostons like this).

    def set_surface(self, new_surface):

        def convert_command_to_poppy_surface(dm_command_dict):
            # Adding the negative relaxed state to any new command in order to compensate for relaxation offset
            # Addition of dicts taken from old JOST version here:
            # https://github.com/spacetelescope/jost-package/blob/aa7cc5517bb474eed971db0f4007ce5fc1226fec/jost/DM_functions.py#L453
            dm_surface = {seg: tuple(np.asarray(self.relaxed_poppy_surface.get(seg, (0., 0., 0.))) + np.asarray(dm_command_dict.get(seg, (0., 0., 0.)))) for
                          seg in set(self.relaxed_poppy_surface) | set(dm_command_dict)}
            return dm_surface

        # Setting the simulated IrisAO means setting each actuator individually
        for seg, values in convert_command_to_poppy_surface(new_surface).items():
            # The IrisAO hardware component and the poppy hex DM object have flipped
            # x/y coordinate axes, so we need to feed what is called "tilt" on the IrisAO
            # into the "tip" argument from poppy and vice versa.
            # Furthermore, depending on poppy version we may need to correct a sign inconsistency
            sign = -1 if Version(poppy.__version__) < Version('1.0') else 1

            piston = sign * values[0] * u.um
            tip = sign * values[2] * u.mrad
            tilt = sign * values[1] * u.mrad
            self.set_actuator(seg-1, piston, tip, tilt)    # offset by -1 for 0-based vs 1-based segment indices; see PR #147

    @staticmethod
    def invert_data(data):
        new_data = {}
        for key, values in data.items():
            new_values = []
            for value in values:
                new_values.append(-value)
            new_data[key] = tuple(new_values)
        return new_data

    def relax(self):
        zeros_list = catkit.hardware.iris_ao.util.create_zero_list(self.number_of_segments)
        zero_dict = catkit.hardware.iris_ao.util.create_dict_from_list(zeros_list)
        self.set_surface(zero_dict)


class PoppyIrisAOEmulator:
    """ Emulates subprocess for particular use by catkit.hardware.iris_ao.iris_ao_controller.IrisAoDmController. """

    PIPE = None
    CREATE_NEW_PROCESS_GROUP = None

    def __init__(self, config_id, dm, driver_serial):
        self.config_id = config_id

        self.stdin = self
        self.stdout = self

        self.disable_hardware = None

        self.path_to_custom_mirror_files = None
        self.filename_ptt_dm = None

        self.driver_serial = driver_serial

        # assert isinstance(dm, PoppyIrisAODM)
        self.dm = dm  # An instance of PoppyIrisAODM.

    def Popen(self,
              args, bufsize=-1, executable=None, stdin=None, stdout=None, stderr=None, preexec_fn=None, close_fds=True,
              shell=False, cwd=None, env=None, universal_newlines=False, startupinfo=None,
              creationflags=0, restore_signals=True, start_new_session=False, pass_fds=(), *, encoding=None,
              errors=None):

        _full_path_dm_exe = args[0]
        self.disable_hardware = catkit.util.str2bool(args[1])

        if len(args) > 2:
            self.path_to_custom_mirror_files = args[2]
            # This file gets read here and only once by the C++ code but only the mirror SN and driver SN are used.
            # Running sim tests may then help prevent damaging mirror/driver/file conflicts.
            ini_file = os.path.join(self.path_to_custom_mirror_files, "CustomFLAT.ini")
            driver_serial_in_ini_file = catkit.hardware.iris_ao.util.get_driver_serial_from_ini_file(ini_file)
            if self.driver_serial.strip("'") != driver_serial_in_ini_file:
                raise ValueError(f"Driver serial mismatch: {self.driver_serial} != {driver_serial_in_ini_file}")
            mirror_serial_in_ini_file = catkit.hardware.iris_ao.util.get_mirror_serial_from_ini_file(ini_file)
            if self.dm.mirror_serial.strip("'") != mirror_serial_in_ini_file:
                raise ValueError(f"Driver serial mismatch: {self.dm.mirror_serial} != {mirror_serial_in_ini_file}")

        if len(args) > 3:
            self.filename_ptt_dm = args[3]

        return self

    def write(self, buffer):
        if self.disable_hardware:
            return

        if buffer == b'quit\n':
            self.dm.relax()
        elif buffer == b'config\n':
            ptt_data = catkit.hardware.iris_ao.util.read_ini(self.filename_ptt_dm, self.dm.number_of_segments)   # this returns a DM command dict
            self.dm.set_surface(ptt_data)
        else:
            raise NotImplementedError(f"Emulation of '{self.config_id}' does not recognise the command '{buffer}'")

    def flush(self):
        pass

    def readline(self):
        return b"success"

    def poll(self):
        pass

    def wait(self, timeout=None):
        pass

class PoppyIrisAoDmController(SimInstrument, IrisAoDmController):
    instrument_lib = PoppyIrisAOEmulator
