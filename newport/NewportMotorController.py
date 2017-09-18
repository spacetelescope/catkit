from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import numpy as np

from hicat.config import CONFIG_INI
from hicat.hardware import testbed_state
from hicat.interfaces.MotorController import MotorController
from .lib import XPS_Q8_drivers

"""Implementation of the Newport motor controller interface."""


class NewportMotorController(MotorController):
    def initialize(self, initialize_to_nominal=True):
        """Creates an instance of the controller library and opens a connection."""

        # Create an instance of the XPS controller.
        myxps = XPS_Q8_drivers.XPS()

        # Grab attributes from the INI.
        ip_address = CONFIG_INI.get(self.config_id, "ip_address")
        port = CONFIG_INI.getint(self.config_id, "port")
        timeout = CONFIG_INI.getint(self.config_id, "timeout")

        # Connect to a socket on the controller server.
        socket_id = myxps.TCP_ConnectToServer(ip_address, port, timeout)

        if self.socket_id == -1:
            raise Exception("Connection to XPS failed, check IP & Port")

        self.socket_id = socket_id
        self.motor_controller = myxps
        print("Initializing Newport XPS Motor Controller " + self.config_id + "...")

        # Initialize and move to nominal positions.
        if initialize_to_nominal:
            motors = [s for s in CONFIG_INI.sections() if s.startswith('motor_')]
            for motor_name in motors:
                self.__move_to_nominal(motor_name)

        # Update the testbed_state for the FPM and Lyot Stop.
        self.__update_testbed_state("motor_lyot_stop_x", self.get_position("motor_lyot_stop_x"))
        self.__update_testbed_state("motor_FPM_Y", self.get_position("motor_FPM_Y"))
        return myxps

    def close(self):
        """Close dm connection safely."""
        self.motor_controller.TCP_CloseSocket(self.socket_id)

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
        if not np.isclose(current_position, position, atol=.001):
            # Move.
            error_code, return_string = self.motor_controller.GroupMoveAbsolute(self.socket_id, positioner, [position])
            if error_code != 0:
                self.__raise_exceptions(error_code, 'GroupMoveAbsolute')
            else:
                print("Moved positioner " + positioner + " to " + str(position))
                self.__update_testbed_state(motor_id, position)

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
        error_code, return_string = self.motor_controller.GroupMoveRelative(self.socket_id, positioner, [distance])
        if error_code != 0:
            self.__raise_exceptions(error_code, 'GroupMoveRelative')
        else:
            print("Moved positioner " + positioner + " by " + str(distance))
            self.__update_testbed_state(motor_id, self.get_position(motor_id))

    def get_position(self, motor_id):
        """
        Get current position
        :param motor_id: String to match in the config ini (ex: motor_FPM_X).
        :return: Current position.
        """
        group = CONFIG_INI.get(motor_id, "group_name")
        positioner = CONFIG_INI.get(motor_id, "positioner_name")
        self.__ensure_initialized(group)

        error_code, current_position = self.motor_controller.GroupPositionCurrentGet(self.socket_id, positioner, 1)
        if error_code != 0:
            self.__raise_exceptions(error_code, 'GroupPositionCurrentGet')
        else:
            print('Positioner ' + positioner + ' is in position ' + str(current_position))
            return current_position

    def __ensure_initialized(self, group):
        error_code, current_status = self.motor_controller.GroupStatusGet(self.socket_id, group)
        if error_code != 0:
            self.__raise_exceptions(error_code, 'GroupStatusGet')

        # Kill motor if it is not in a known good state.
        if current_status != 11 and current_status != 12 and current_status != 7 and current_status != 42:
            error_code, return_string = self.motor_controller.GroupKill(self.socket_id, group)
            if error_code != 0:
                self.__raise_exceptions(error_code, 'GroupKill')
            print("Killed group " + group + " because it was not in state 11, 12, or 7")

            # Update the status.
            error_code, current_status = self.motor_controller.GroupStatusGet(self.socket_id, group)
            if error_code != 0:
                self.__raise_exceptions(error_code, 'GroupStatusGet')

        # Initialize from killed state.
        if current_status == 7:
            # Initialize the group
            error_code, return_string = self.motor_controller.GroupInitialize(self.socket_id, group)
            if error_code != 0:
                self.__raise_exceptions(error_code, 'GroupInitialize')
            print("Initialized group " + group)

            # Update the status
            error_code, current_status = self.motor_controller.GroupStatusGet(self.socket_id, group)
            if error_code != 0:
                self.__raise_exceptions(error_code, 'GroupStatusGet')

        # Home search
        if current_status == 42:
            error_code, return_string = self.motor_controller.GroupHomeSearch(self.socket_id, group)
            if error_code != 0:
                self.__raise_exceptions(error_code, 'GroupHomeSearch')
            print("Homed group " + group)

    def __move_to_nominal(self, group_config_id):
        self.__ensure_initialized(CONFIG_INI.get(group_config_id, "group_name"))
        nominal = CONFIG_INI.getfloat(group_config_id, "nominal")
        self.absolute_move(group_config_id, nominal)

    # Migrated from Newport demo code, now raises exceptions instead of print statements.
    def __raise_exceptions(self, error_code, api_name):
        if (error_code != -2) and (error_code != -108):
            error_code2, error_string = self.motor_controller.ErrorStringGet(self.socket_id, error_code)
            if error_code2 != 0:
                raise Exception(api_name + ': ERROR ' + str(error_code))
            else:
                raise Exception(api_name + ': ' + error_string)
        else:
            if error_code == -2:
                raise Exception(api_name + ': TCP timeout')
            if error_code == -108:
                raise Exception(api_name + ': The TCP/IP connection was closed by an administrator')
        raise Exception("Unknown error_code returned from Newport Motor Controller.")

    # Only a few of the motor IDs have testbed state entries.  
    @staticmethod
    def __update_testbed_state(motorid, position):
        if motorid == "motor_lyot_stop_x":
            nominal = CONFIG_INI.getfloat(motorid, "nominal")
            testbed_state.lyot_stop = True if np.isclose(nominal, position, atol=.001) else False
        elif motorid == "motor_FPM_Y":
            nominal = CONFIG_INI.getfloat(motorid, "nominal")
            testbed_state.coronograph = True if np.isclose(nominal, position, atol=.001) else False
