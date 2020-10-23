import abc

import catkit.hardware.iris_ao.util

class IrisAOEmulator(abc.ABC):
    """ Emulates subprocess for particular use by catkit.hardware.iris_ao.iris_ao_controller.IrisAoDmController. """

    PIPE = "PIPE"
    CREATE_NEW_PROCESS_GROUP = "CREATE_NEW_PROCESS_GROUP"

    def __init__(self, config_id):
        self.config_id = config_id

        self.stdin = self
        self.stdout = self

        self.enable_hardware = None

        self.path_to_ini_files = None
        self.filename_ptt_dm = None

        self.ini_data = None
        self.ptt_data = None

        self.number_of_segments = catkit.hardware.iris_ao.util.iris_num_segments(config_id)

    def Popen(self,
              args, bufsize=-1, executable=None, stdin=None, stdout=None, stderr=None, preexec_fn=None, close_fds=True,
              shell=False, cwd=None, env=None, universal_newlines=False, startupinfo=None,
              creationflags=0, restore_signals=True, start_new_session=False, pass_fds=(), *, encoding=None,
              errors=None):

        _full_path_dm_exe = args[0]
        self.enable_hardware = args[1]

        if len(cmd) > 2:
            self.path_to_ini_files = args[2]
            # This file gets read here and only once by the C++ code.
            self.ini_data = catkit.hardware.iris_ao.util.read_ini(path=path_to_ini_files,
                                                                  number_of_segments=self.number_of_segments)

        if len(cmd) > 3:
            self.filename_ptt_dm = args[3]

        return self

    def write(self, buffer):
        if not self.enable_hardware:
            # Simulate a un-flattened/natural DM surface.
            self.quit()
            return

        if buffer == b'quit\n':
            self.quit()
        elif buffer == b'config\n':
            self.config()
        else:
            raise NotImplementedError(f"Emulation of '{self.config_id}' does not recognise the command '{buffer}'")

    def flush(self):
        pass

    @abs.abstractmethod
    def quit(self):
        pass

    @abs.abstractmethod
    def config(self):
        pass
