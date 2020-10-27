import poppy

import catkit.hardware.iris_ao.iris_ao_controller
import catkit.hardware.iris_ao.util
from catkit.interfaces.Instrument import SimInstrument


class PoppyIrisAODM(poppy.dms.HexSegmentedDeformableMirror):

    @property
    def number_of_segments(self):
        return self.dm_shape

    def __init__(self, mcf_filename, custom_flat_filename, **super_kwargs):
        super().__init__(**super_kwargs)

        self.mirror_serial = None

        # Read the manufacturers .mcf "flat" file.
        # This is implicitly applied by the driver/controller and is NOT a present contribution of the command sent to
        # the driver/controller by catkit.hardware.iris_ao.iris_ao_controller.IrisAoDmController.
        self.mcf_filename = mcf_filename
        #mcf_data, self.mirror_serial = catkit.hardware.iris_ao.util.read_mcf(self.mcf_filename, self.number_of_segments)
        #mcf_relaxed_poppy_surface = -self.convert_command_to_poppy_surface(mcf_data, _include_relaxation=False)

        self.custom_flat_filename = custom_flat_filename
        custom_flat_data = catkit.hardware.iris_ao.util.read_ini(self.custom_flat_filename, self.number_of_segments)
        custom_flat_relaxed_poppy_surface = -self.convert_command_to_poppy_surface(custom_flat_data, _include_relaxation=False)

        # A flat Poppy surfaces := 0.
        self.relaxed_poppy_surface = custom_flat_relaxed_poppy_surface  # + mcf_relaxed_poppy_surface
        self.relax()  # ??? See https://github.com/spacetelescope/catkit/issues/63 (we don't currently relax the bostons like this).

    def convert_command_to_poppy_surface(self, _include_relaxation=True):
        # _include_relaxation exists only such that this func can be used to get the relaxed surface in the first place.

        # pseudocode...
        poppy_surface = # convert command to surface.

        # Poppy surfaces are zero based so a relaxed surface is negative.
        if _include_relaxation:
            # The .mcf "flat" file is implicitly applied by the driver/controller and is NOT a present contribution of
            # the command sent to the driver/controller by catkit.hardware.iris_ao.iris_ao_controller.IrisAoDmController.
            # We need to also implicitly include this contribution since we mimic a relaxed surface.
            poppy_surface -= self.relaxed_poppy_surface

        return poppy_surface

    def relax(self):
        self.set_surface(self.relaxed_poppy_surface)


class PoppyIrisAOEmulator:
    """ Emulates subprocess for particular use by catkit.hardware.iris_ao.iris_ao_controller.IrisAoDmController. """

    PIPE = None
    CREATE_NEW_PROCESS_GROUP = None

    def __init__(self, config_id, dm, driver_serial):
        self.config_id = config_id

        self.stdin = self
        self.stdout = self

        self.enable_hardware = None

        self.path_to_custom_mirror_files = None
        self.filename_ptt_dm = None

        self.driver_serial = driver_serial

        assert isinstance(dm, PoppyIrisAODM)
        self.dm = dm  # An instance of PoppyIrisAODM.

    def Popen(self,
              args, bufsize=-1, executable=None, stdin=None, stdout=None, stderr=None, preexec_fn=None, close_fds=True,
              shell=False, cwd=None, env=None, universal_newlines=False, startupinfo=None,
              creationflags=0, restore_signals=True, start_new_session=False, pass_fds=(), *, encoding=None,
              errors=None):

        _full_path_dm_exe = args[0]
        self.enable_hardware = args[1]

        if len(cmd) > 2:
            self.path_to_custom_mirror_files = args[2]
            # This file gets read here and only once by the C++ code but only the mirror SN and driver SN are used.
            # Running sim tests may then help prevent damaging mirror/driver/file conflicts.
            assert self.driver_serial == get_driver_serial_from_ini_file
            assert self.dm.mirror_serial == get_mirror_serial_from_ini_file

        if len(cmd) > 3:
            self.filename_ptt_dm = args[3]

        return self

    def write(self, buffer):
        if not self.enable_hardware:
            return

        if buffer == b'quit\n':
            self.dm.relax()
        elif buffer == b'config\n':
            ptt_data = catkit.hardware.iris_ao.util.read_ptt111(self.filename_ptt_dm, self.dm.number_of_segments)
            self.dm.set_surface(self.dm.convert_command_to_poppy_surface(ptt_data))
        else:
            raise NotImplementedError(f"Emulation of '{self.config_id}' does not recognise the command '{buffer}'")

    def flush(self):
        pass


class IrisAoDmController(SimInstrument, catkit.hardware.iris_ao.iris_ao_controller.IrisAoDmController):
    instrument_lib = PoppyIrisAOEmulator
