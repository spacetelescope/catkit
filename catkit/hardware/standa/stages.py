# stageClass.py
# 1/11/2022
# Aidan Gray
# aidan.gray@idg.jhu.edu
#
# Generic Stage Class

import ctypes
import logging
import math
import os
import sys

from catkit.interfaces.Instrument import Instrument

try:
    library_path = os.environ.get('CATKIT_PYXIMC_LIB_PATH')
    if library_path:
        sys.path.append(library_path)
    import pyximc
except Exception as error:
    pyximc = error

# cur_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
# os.chdir(cur_dir)
# ximcDir = (f'{cur_dir}/ximc-2.13.3/ximc')
# ximcPackageDir = os.path.join(ximcDir, "crossplatform", "wrappers", "python")
# sys.path.append(ximcPackageDir)
# import pyximc  # noqa: E402


class Stage(Instrument):

    instrument_lib = pyximc

    def initialize(self, deviceID, softStops, homeOffset, conversionFactor, units):
        if isinstance(self.instrument_lib, Exception):
            raise self.instrument_lib

        self.deviceID = deviceID
        self.softStops = softStops
        self.u_homeOffset, self.homeOffset = math.modf(homeOffset)
        self.conversionFactor = conversionFactor
        self.units = units

    def _open(self):
        return self.instrument_lib.lib.open_device(self.deviceID)

    def _close(self):
        # TODO: Do we not need to close something here?
        ...

    def home(self):
        """
        Homes the stage.
        """

        respHmst, hmst = self.get_home_settings()

        # print(f'FastHome=   {hmst.FastHome} \
        #       \nuFastHome=  {hmst.uFastHome} \
        #       \nSlowHome=   {hmst.SlowHome} \
        #       \nuSlowHome=  {hmst.uSlowHome} \
        #       \nHomeDelta=  {hmst.HomeDelta} \
        #       \nuHomeDelta= {hmst.uHomeDelta} \
        #       \nHomeFlags=  {hmst.HomeFlags}')

        # hmst.FastHome = int(100)
        # hmst.uFastHome = int(0)
        # hmst.SlowHome = int(100)
        # hmst.uSlowHome = int(0)
        hmst.HomeDelta = int(self.homeOffset)
        hmst.uHomeDelta = int(self.u_homeOffset)
        # hmst.HomeFlags = int(370)

        result = self.instrument_lib.lib.command_homezero(self.instrument)

        if result != self.instrument_lib.Result.Ok:
            raise RuntimeError("command_homezero failed")

    def get_home_settings(self):
        hmst = self.instrument_lib.home_settings_t()
        
        result = self.instrument_lib.lib.get_home_settings(self.instrument, ctypes.byref(hmst))
        
        if result != self.instrument_lib.Result.Ok:
            raise RuntimeError("get_home_settings() failed")

        return hmst

    def offset_steps(self, distance):
        currentPosition = self.get_enc_position()
        newPosition = currentPosition + distance
        return self.goto_steps(newPosition)

    def absolute_move(self, position):
        """
        Sends a move command for the given steps.

        :param position: int, float - Position to go to (In steps as a decimal).
        """

        # split the integer from the decimal
        u_pos, pos = math.modf(position)

        # convert the decimal to #/256
        u_pos = u_pos * 256

        result = self.instrument_lib.lib.command_move(self.instrument, int(pos), int(u_pos))
        if result != self.instrument_lib.Result.Ok:
            raise RuntimeError("command_move() failed")
    
    def offset_real(self, distance):
        distance = distance / self.conversionFactor
        return self.offset_steps(distance)

    def relative_move(self, position):
        """
        Sends a move command for the given real value.

        Input:
        :param position: int, float (In steps as a decimal).
        """
        position = position / self.conversionFactor
        self.log.info(f'goto_steps: {position}')
        return self.goto_steps(position)
    
    def set_speed(self, speed):
        """
        Sets the speed in steps/s.

        :param speed: int - Speed (as a decimal) in steps/s
        """

        mvst = self.instrument_lib.move_settings_t()
        result = self.instrument_lib.lib.get_move_settings(self.instrument, ctypes.byref(mvst))

        if result != self.instrument_lib.Result.Ok:
            raise RuntimeError("get_move_settings() failed")

        # split the integer from the decimal
        u_speed, speed = math.modf(speed)

        # convert the decimal to #/256
        u_speed = u_speed * 256

        # prepare move_settings_t struct
        mvst.Speed = int(speed)
        mvst.uSpeed = int(u_speed)
        result = self.instrument_lib.lib.set_move_settings(self.instrument, ctypes.byref(mvst))
        if result != self.instrument_lib.Result.Ok:
            raise RuntimeError("set_move_settings() failed")

    def get_speed(self):
        """
        Returns the speed in steps/s.

        Output:
        - mvst.Speed    Speed in steps
        - mvst.uSpeed   Leftover uSteps
        """
        mvst = self.instrument_lib.move_settings_t()
        result = self.instrument_lib.lib.get_move_settings(self.instrument, ctypes.byref(mvst))

        if result != self.instrument_lib.Result.Ok:
            raise RuntimeError("get_move_settings() failed")

        return mvst.Speed, mvst.uSpeed

    def get_move_status(self):
        """
        Returns the moving status of the given device

        :return: str "BUSY" | "IDLE"
        """
        deviceStatus = self.instrument_lib.status_t()
        result = self.instrument_lib.lib.get_status(self.instrument, ctypes.byref(deviceStatus))

        if result != self.instrument_lib.Result.Ok:
            raise RuntimeError("get_status() failed")

        moveComState = deviceStatus.MvCmdSts

        if moveComState == 129:
            stageStatus = 'BUSY'
        else:
            stageStatus = 'IDLE'
        
        return stageStatus

    def is_moving(self):
        return self.get_move_status() == "BUSY"

    def get_step_position(self):
        """
        Returns the position of the device in steps

        :return: stagePosition Position of the stage
        """
        stagePositionTmp = self.instrument_lib.get_position_t()
        result = self.instrument_lib.lib.get_position(self.instrument, ctypes.byref(stagePositionTmp))

        if result != self.instrument_lib.Result.Ok:
            raise RuntimeError("get_position() failed")

        # Convert the position from steps to readable units (conversionFactor)
        stagePosition = stagePositionTmp.Position + (stagePositionTmp.uPosition / 256)

        return stagePosition

    def get_enc_position(self):
        """
        Returns the position of the device in steps

        :return: stagePosition Position of the stage
        """
        stagePositionTmp = self.instrument_lib.get_position_t()
        result = self.instrument_lib.lib.get_position(self.instrument, ctypes.byref(stagePositionTmp))

        if result != self.instrument_lib.Result.Ok:
            raise RuntimeError("get_position() failed")

        return stagePositionTmp.EncPosition

    def get_position(self):
        """
        Returns the position of the device

        :return: stagePosition Position of the stage
        """
        return self.conversionFactor * self.get_enc_position()[1]

    def stop(self):
        result = self.instrument_lib.lib.command_sstp(self.instrument)
        if result != self.instrument_lib.Result.Ok:
            raise RuntimeError("Soft stop failed")
