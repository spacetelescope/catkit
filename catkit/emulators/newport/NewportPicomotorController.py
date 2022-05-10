import urllib

from catkit.hardware.newport.NewportPicomotorController import Command


class NewportPicoMotorControllerEmulator:

    N_AXIS = 4

    def __init__(self, home_position):
        self.cmd = None
        self.axis = None
        self._daisy = None
        self.position = [0] * self.N_AXIS
        self.home_position = home_position

    @property
    def daisy(self):
        return self._daisy

    @daisy.setter
    def daisy(self, value):
        if value is not None:
            raise NotImplementedError()

    def urlopen(self, url, **kwargs):
        if "cmd_send" not in url:
            return

        query = url.split("cmd_send.cgi?")[1]
        query_dict = urllib.parse.parse_qs(query)

        message = query_dict["cmd"]

        # There are only three formats:
        # 1) message := command
        # 2) message := daisy_str + axis_int + command + "?"
        # 3) message := daisy_str + axis_int + command + value_str
        # where daisy_str := f"{int}>" | '' and ints are single digit only.

        try:
            # 1) message := command
            cmd = Command(message)

            if cmd is Command.reset:
                self.reset()
            else:
                raise NotImplementedError()
        except ValueError:
            # 2) message := daisy_int + axis_int + command + "?"
            # 3) message := daisy_int + axis_int + command + value_str

            is_get = message.endswith('?')
            if is_get:
                self.cmd = Command(message[-3:-1])
                self.axis = int(message[-4])
                self.daisy = int(message[-5]) if len(message) == 5 else None

                if cmd in (Command.exact_move, Command.relative_move):
                    self.get_position(self.daisy, self.axis)
                elif cmd is Command.home_position:
                    self.get_home_position(self.daisy, self.axis)
                elif cmd is Command.error_message:
                    self.get_error_message()
                else:
                    raise NotImplementedError()
            else:
                if Command.relative_move.value in message:
                    self.daisy, self.axis, value = self._parse_data(message, Command.relative_move)
                    self.relative_move(self.daisy, self.axis, value)
                elif Command.exact_move.value in message:
                    self.daisy, self.axis, value = self._parse_data(message, Command.exact_move)
                    self.absolute_move(self.daisy, self.axis, value)
                elif Command.home_position.value in message:
                    self.daisy, self.axis, value = self._parse_data(message, Command.home_position)
                    self.home(self.daisy, self.axis, value)
                else:
                    raise NotImplementedError()

        return self

    def _parse_data(self, message, cmd):
        daisy_axis, value = message.split(cmd.value)
        if len(daisy_axis) == 2:
            daisy = daisy_axis[0]
            axis = daisy_axis[1]
        else:
            daisy = None
            axis = daisy_axis[0]

        return daisy, axis, value

    def read(self):
        if self.cmd is Command.error_message:
            data = "ERROR"
        elif self.cmd in (Command.exact_move, Command.relative_move):
            data = self.position[self.axis]
        elif self.cmd is Command.home_position:
            data = self.home_position[self.axis]

        return f"response-->{data}\\r"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def reset(self):
        """ Injection layer, override to interface with simulator. """
        ...

    def relative_move(self, daisy, axis, value):
        """ Injection layer, override to interface with simulator. """
        self.daisy = daisy
        self.axis = axis
        self.cmd = Command.relative_move

        self.position[axis] += value

    def absolute_move(self, daisy, axis, value):
        """ Injection layer, override to interface with simulator. """
        self.daisy = daisy
        self.axis = axis
        self.cmd = Command.exact_move

        self.position[axis] = value

    def define_home(self, daisy, axis, value):
        """ Injection layer, override to interface with simulator. """
        self.home_position[axis] = value

    def get_position(self, daisy, axis):
        """ Injection layer, override to interface with simulator. """
        pass

    def get_error_message(self):
        """ Injection layer, override to interface with simulator. """
        pass

    def get_home_position(self, daisy, axis):
        """ Injection layer, override to interface with simulator. """
        pass
