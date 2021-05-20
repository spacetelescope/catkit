import logging


class NewportMotorControllerEmulator:
    """ Emulates Newport's XPS driver specifically for their XPS Q8 motot controller. """

    def __init__(self):
        self.current_position = {}
        self.log = logging.getLogger()

    def XPS(self, *args, **kwargs):
        return self

    def TCP_ConnectToServer(self, host_ip, port, timeout, *args, **kwargs):
        return self

    def TCP_CloseSocket(self, socket_id, *args, **kwargs):
        pass

    def GroupMoveAbsolute(self, socket_id, positioner, position, *args, **kwargs):
        position = position[0]
        self.current_position[positioner] = position
        self.sim_absolute_move(positioner, position)
        return 0, ""

    def GroupMoveRelative(self, socket_id, positioner, distance, *args, **kwargs):
        distance = distance[0]
        self.current_position[positioner] += distance
        self.sim_relative_move(positioner, distance)
        return 0, ""

    def GroupStatusGet(self, socket_id, group, *args, **kwargs):
        return 0, 11

    def GroupPositionCurrentGet(self, socket_id, positioner, *args, **kwargs):
        current_position = self.current_position.get(positioner)
        if current_position is None:
            current_position = 0.
            self.current_position[positioner] = current_position
        return 0, current_position

    def GroupKill(self, socket_id, group, *args, **kwargs):
        return 0, ""

    def GroupInitialize(self, socket_id, group, *args, **kwargs):
        return 0, ""

    def GroupHomeSearch(self, socket_id, group, *args, **kwargs):
        return 0, ""

    def ErrorStringGet(self, socket_id, error_code, *args, **kwargs):
        return 0, "ERROR"

    def sim_relative_move(self, positioner, distance):
        """ Implement to make changes to the simulated system, e.g., a Poppy model. """

    def sim_absolute_move(self, positioner, position):
        """ Implement to make changes to the simulated system, e.g., a Poppy model. """
