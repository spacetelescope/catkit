import os
import sys

import numpy as np

from catkit.config import CONFIG_INI
from catkit.interfaces.MotorController import MotorController

"""Implementation of the Newport motor controller interface."""

# Import XPS Q8 driver
try:
    library_path = os.environ.get('CATKIT_NEWPORT_LIB_PATH')
    if library_path:
        sys.path.append(library_path)
    import XPS_Q8_drivers
except Exception as error:
    XPS_Q8_drivers = error


class NewportMotorController(MotorController):

    instrument_lib = XPS_Q8_drivers

    OK_STATES = (7, 11, 12, 42)

    def __init__(self, *args, **kwargs):
        if isinstance(self.instrument_lib, BaseException):
            raise self.instrument_lib
        super().__init__(*args, **kwargs)

    def initialize(self, host, port, timeout=60, initialize_to_nominal=True, atol=0.001):
        """Creates an instance of the controller library and opens a connection."""

        self.host = host
        self.port = port
        self.timeout = timeout
        self.initialize_to_nominal = initialize_to_nominal
        self.atol = atol

    def _open(self):
        # Create an instance of the XPS controller.
        self.instrument = self.instrument_lib.XPS()

        # Connect to a socket on the controller server.
        socket_id = self.instrument.TCP_ConnectToServer(self.host, self.port, self.timeout)
        if socket_id == -1:
            raise Exception(f"Connection to XPS failed, check IP & Port (invalid socket '{socket_id}')")
        self.socket_id = socket_id

        # Initialize and move to nominal positions.
        if self.initialize_to_nominal:
            self.log.info(f"Initializing Newport XPS Motor Controller {self.config_id}...")
            motors = [s for s in CONFIG_INI.sections() if s.startswith('motor_')]
            for motor_name in motors:
                self.__move_to_nominal(motor_name)

        return self.instrument

    def _close(self):
        """Close dm connection safely."""
        try:
            self.instrument.TCP_CloseSocket(self.socket_id)
        finally:
            self.socket_id = None

    def absolute_move(self, motor_id, position):
        """
        Moves motor to specified position.  Skips if already in position (or close enough).
        :param motor_id: String to match in the config ini (ex: motor_FPM_X).
        :param position: Target position to move to.
        """
        group = CONFIG_INI.get(motor_id, "group_name")
        positioner = CONFIG_INI.get(motor_id, "positioner_name")
        self.__ensure_initialized(group)

        current_position = self.get_position(motor_id)
        if not np.isclose(current_position, position, atol=self.atol):
            # Move.
            self.log.info(f"Moving positioner '{positioner}' by '{position}'...")
            error_code, return_string = self.instrument.GroupMoveAbsolute(self.socket_id, positioner, [position])
            self.__raise_on_error(error_code, 'GroupMoveAbsolute')

    def relative_move(self, motor_id, distance):
        """
        Moves motor by the specified distance.
        :param motor_id: String to match in the config ini (ex: motor_FPM_X).
        :param distance: Distance to move motor, can be positive or negative.
        """
        group = CONFIG_INI.get(motor_id, "group_name")
        positioner = CONFIG_INI.get(motor_id, "positioner_name")
        self.__ensure_initialized(group)

        # Move.
        self.log.info(f"Moving positioner '{positioner}' by '{distance}'...")
        error_code, return_string = self.instrument.GroupMoveRelative(self.socket_id, positioner, [distance])
        self.__raise_on_error(error_code, 'GroupMoveRelative')

    def get_position(self, motor_id):
        """
        Get current position
        :param motor_id: String to match in the config ini (ex: motor_FPM_X).
        :return: Current position.
        """
        group = CONFIG_INI.get(motor_id, "group_name")
        positioner = CONFIG_INI.get(motor_id, "positioner_name")
        self.__ensure_initialized(group)

        error_code, current_position = self.instrument.GroupPositionCurrentGet(self.socket_id, positioner, 1)
        self.__raise_on_error(error_code, 'GroupPositionCurrentGet')
        return current_position

    def __ensure_initialized(self, group):
        error_code, current_status = self.instrument.GroupStatusGet(self.socket_id, group)
        self.__raise_on_error(error_code, 'GroupStatusGet')

        # Kill motor if it is not in a known good state.
        if current_status not in self.OK_STATES:
            error_code, return_string = self.instrument.GroupKill(self.socket_id, group)
            self.__raise_on_error(error_code, 'GroupKill')
            self.log.warning(f"Killed group '{group}' because it was not in state '{self.OK_STATES}'")

            # Update the status.
            error_code, current_status = self.instrument.GroupStatusGet(self.socket_id, group)
            self.__raise_on_error(error_code, 'GroupStatusGet')

        # Initialize from killed state.
        if current_status == 7:
            # Initialize the group
            error_code, return_string = self.instrument.GroupInitialize(self.socket_id, group)
            self.__raise_on_error(error_code, 'GroupInitialize')
            self.log.info(f"Initialized group '{group}'")

            # Update the status
            error_code, current_status = self.instrument.GroupStatusGet(self.socket_id, group)
            self.__raise_on_error(error_code, 'GroupStatusGet')

        # Home search
        if current_status == 42:
            error_code, return_string = self.instrument.GroupHomeSearch(self.socket_id, group)
            self.__raise_on_error(error_code, 'GroupHomeSearch')
            self.log.info(f"Homed group '{group}'")

    def __move_to_nominal(self, group_config_id):
        self.__ensure_initialized(CONFIG_INI.get(group_config_id, "group_name"))
        nominal = CONFIG_INI.getfloat(group_config_id, "nominal")
        self.absolute_move(group_config_id, nominal)

    # Migrated from Newport demo code, now raises exceptions and does logging elsewhere.
    def __raise_on_error(self, error_code, api_name):
        if error_code == 0:
            return

        if error_code == -2:
            raise Exception(f"{api_name}: TCP timeout")
        elif error_code == -108:
            raise Exception(f"{api_name}: The TCP/IP connection was closed by an administrator")
        else:
            error_code2, error_string = self.instrument.ErrorStringGet(self.socket_id, error_code)
            if error_code2 != 0:
                raise Exception(f"{api_name}: ERROR '{error_code}'")
            else:
                raise Exception(f"{api_name}: '{error_string}'")
