# stageClass.py
# 1/11/2022
# Aidan Gray
# aidan.gray@idg.jhu.edu
#
# Generic Stage Class

import logging
import sys
import os
import math
from ctypes import *

cur_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
os.chdir(cur_dir)
ximcDir = (f'{cur_dir}/ximc-2.13.3/ximc')
ximcPackageDir = os.path.join(ximcDir, "crossplatform", "wrappers", "python")
sys.path.append(ximcPackageDir)
from pyximc import *

class Stage:
    def __init__(self, lib, deviceID, name, softStops, homeOffset, conversionFactor, units):
        self.logger = logging.getLogger('stages')
        self.lib = lib
        self.deviceID = deviceID
        self.name = name
        self.softStops = softStops
        self.u_homeOffset, self.homeOffset = math.modf(homeOffset)
        self.conversionFactor = conversionFactor
        self.units = units

        self.stageDev = self.lib.open_device(deviceID)

    def home(self):
        """
        Homes the stage.
        """
        response = 'OK'
        respHmst, hmst = self.get_home_settings()
        if respHmst == 'OK':
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

            result = lib.command_homezero(self.stageDev)

            if result == Result.Ok:
                pass
            else:
                response = 'BAD: command_homezero failed'
        else:
            response = respHmst

        return response

    def get_home_settings(self):
        response = 'OK'
        hmst = home_settings_t()
        
        result = lib.get_home_settings(self.stageDev, byref(hmst))
        
        if result == Result.Ok:
            pass
        else:
            response = 'BAD: get_home_settings() failed'

        return response, hmst

    def offset_steps(self, distance):
        currentPositionResp, currentPosition = self.get_enc_position()

        if currentPositionResp == 'OK':
            newPosition = currentPosition + distance
            result = self.goto_steps(newPosition)
        else:
            result = currentPositionResp

        return result

    def goto_steps(self, position):
        """
        Sends a move command for the given steps.

        Input:
        - position  In steps as a decimal

        Output:
        - OK/BAD
        """

        # split the integer from the decimal
        u_pos, pos = math.modf(position)

        # convert the decimal to #/256
        u_pos = u_pos * 256

        result = lib.command_move(self.stageDev, int(pos), int(u_pos))
        if result == Result.Ok:
            return 'OK'
        else:
            return 'BAD: Move command failed'
    
    def offset_real(self, distance):
        distance = distance / self.conversionFactor
        return self.offset_steps(distance)

    def goto_real(self, position):
        """
        Sends a move command for the given real value.

        Input:
        - position  In steps as a decimal

        Output:
        - OK/BAD
        """
        position = position / self.conversionFactor
        print(f'goto_steps: {position}')
        return self.goto_steps(position)
    
    def set_speed(self, speed):
        """
        Sets the speed in steps/s.

        Inputs:
        - speed     Speed (as a decimal) in steps/s

        Output:
        - OK/BAD
        """

        mvst = move_settings_t()
        result = lib.get_move_settings(self.stageDev, byref(mvst))

        if result == Result.Ok:
            # split the integer from the decimal
            u_speed, speed = math.modf(speed)

            # convert the decimal to #/256
            u_speed = u_speed * 256

            # prepare move_settings_t struct
            mvst.Speed = int(speed)
            mvst.uSpeed = int(u_speed)
            result = lib.set_move_settings(self.stageDev, byref(mvst))
            if result == Result.Ok:
                return 'OK'
            else:
                return 'BAD: set_move_settings() failed'
        else:
            return 'BAD: get_move_settings() failed'

    def get_speed(self):
        """
        Returns the speed in steps/s.

        Output:
        - mvst.Speed    Speed in steps
        - mvst.uSpeed   Leftover uSteps
        """
        response = 'OK'
        mvst = move_settings_t()
        result = lib.get_move_settings(self.stageDev, byref(mvst))

        if result == Result.Ok:    
            stageSpeed = (mvst.Speed, mvst.uSpeed)
        else:
            stageSpeed = (-999,-999)
            response = 'BAD: get_move_settings() failed'
        
        return response, stageSpeed

    def get_move_status(self):
        """
        Returns the moving status of the given device

        Output:
        - BUSY/IDLE
        """
        response = 'OK'
        deviceStatus = status_t()
        result = lib.get_status(self.stageDev, byref(deviceStatus))

        if result == Result.Ok:
            moveComState = deviceStatus.MvCmdSts

            if moveComState == 129:
                stageStatus = 'BUSY'
            else:
                stageStatus = 'IDLE'
        else:
            response = 'BAD: get_status() failed'
            stageStatus = 'N/A'
        
        return response, stageStatus

    def get_step_position(self):
        """
        Returns the position of the device in steps

        Output:
        - response      OK/BAD
        - stagePosition Position of the stage   
        """
        response = 'OK'
        stagePositionTmp = get_position_t()
        result = lib.get_position(self.stageDev, byref(stagePositionTmp))

        if result == Result.Ok:
            # Convert the position from steps to readable units (conversionFactor)
            stagePosition = stagePositionTmp.Position + (stagePositionTmp.uPosition / 256)
        else:
            response = 'BAD: get_position() failed'
            stagePosition = -999
        
        return response, stagePosition

    def get_enc_position(self):
        """
        Returns the position of the device in steps

        Output:
        - response      OK/BAD
        - stagePosition Position of the stage   
        """
        response = 'OK'
        stagePositionTmp = get_position_t()
        result = lib.get_position(self.stageDev, byref(stagePositionTmp))

        if result == Result.Ok:
            stagePosition = stagePositionTmp.EncPosition
        else:
            response = 'BAD: get_position() failed'
            stagePosition = -999
        
        return response, stagePosition

    def get_position(self):
        """
        Returns the position of the device

        Output:
        - response      OK/BAD
        - stagePosition Position of the stage   
        """
        response = 'OK'
        respEncPos = self.get_enc_position()

        if 'BAD' not in respEncPos:
            stagePosition = self.conversionFactor * respEncPos[1]
        else:
            response = respEncPos[0]
            stagePosition = -999

        return response, stagePosition

    def get_units(self):
        return self.units

    def stop(self):
        result = lib.command_sstp(self.stageDev)
        if result == Result.Ok:
            return 'OK'
        else:
            return 'BAD: Soft stop failed'
