#!/usr/bin/python3
# lamp_server.py
# 5/13/2021
# Aidan Gray
# aidan.gray@idg.jhu.edu
# 
# This is a server to control the STUF Project's Laser Driven Light Source.

import asyncio
import pigpio
import time
import sys
import os
import logging
import numpy as np
from datetime import datetime

GPIO = {
    'lamp_state': 6,
    'laser_state': 5,
    'lamp_fault': 25,
    'controller_fault': 24,
    'lamp_operate': 22,
    'interlock_operate': 27
}

def log_start():
    """
    Create a logfile that the rest of the script can write to.

    Output:
    - log 	Object used to access write abilities
    """

    scriptDir = os.path.dirname(os.path.abspath(__file__))
    scriptName = os.path.splitext(os.path.basename(__file__))[0]
    log = logging.getLogger('lamp_server')
    hdlr = logging.FileHandler(scriptDir+'/logs/'+scriptName+'.log')
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    hdlr.setFormatter(formatter)
    log.addHandler(hdlr)
    log.setLevel(logging.INFO)
    return log

def get_status():
    # Laser Status
    # Lamp Status
    # Interlock Status
    # Controller Status
    resp1 = 'INTERLOCK = ' + get_interlock_status()
    resp2 = 'LASER = ' + get_laser_status()
    resp3 = 'LAMP = ' + get_lamp_status() 
    resp4 = 'LAMP_FAULT = ' + get_lamp_fault()
    resp5 = 'CONTROLLER_FAULT = ' + get_controller_fault()
    resp = resp1 + ';' + resp2 + ';' + resp3 + ';' + resp4 + ';' + resp5 + '\n'
    return resp

def get_laser_status():
    try:
        pinNum = GPIO['laser_state']
        pinRead = pi.read(pinNum)
        if pinRead == 0:
            resp = 'OK: ON\n'
        else:
            resp = 'OK: OFF\n'
    except:
        resp = 'BAD'
    return resp

def get_lamp_status():
    try:
        pinNum = GPIO['lamp_state']
        pinRead = pi.read(pinNum)
        if pinRead == 0:
            resp = 'OK: ON\n'
        else:
            resp = 'OK: OFF\n'
    except:
        resp = 'BAD'
    return resp

def get_lamp_fault():
    try:
        pinNum = GPIO['lamp_fault']
        pinRead = pi.read(pinNum)
        if pinRead == 0:
            resp = 'OK: NO FAULT\n'
        else:
            resp = 'OK: FAULT\n'
    except:
        resp = 'BAD'
    return resp

def get_interlock_status():
    try:
        pinNum = GPIO['interlock']
        pinRead = pi.read(pinNum)
        if pinRead == 0:
            resp = 'OK: OFF\n'
        else:
            resp = 'OK: ON\n'
    except:
        resp = 'BAD'
    return resp

def get_controller_status():
    try:
        pinNum = GPIO['controller_fault']
        pinRead = pi.read(pinNum)
        if pinRead == 0:
            resp = 'OK: NO FAULT\n'
        else:
            resp = 'OK: FAULT\n'
    except:
        resp = 'BAD'
    return resp

def set_lamp(state):
    try:
        pinNum = GPIO['lamp_operate']
        pi.write(pinNum, state)
        resp = 'OK'
    except:
        resp = 'BAD'
    return resp

def set_interlock(state):
    try:
        pinNum = GPIO['interlock']
        pi.write(pinNum, state)
        resp = 'OK'
    except:
        resp = 'BAD'
    return resp

def initialize_gpio():
    for pin in GPIO:
        pinNum = GPIO[pin]
        if pinNum == 22 or pinNum == 27:
            pi.set_mode(pinNum, pigpio.INPUT)
        else:
            pi.set_mode(pinNum, pigpio.OUTPUT)

def handle_command(log, writer, data): 
    """
    Determines what to do with the incoming data - setting a parameter. 

    Input:
    - log       object to access the logger
    - writer    object to write data back to the client
    - data      the data received from the client
    """

    response = 'BAD: Invalid Command'
    commandList = data.split()

    try:
        # check if command is Set or not
        if commandList[0] == 'set':
            if len(commandList) >= 1:
                response = setParams(commandList[1:])
    except IndexError:
        response = 'BAD: Invalid Command'
        
    # tell the client the result of their command & log it
    #log.info('RESPONSE = '+response)
    writer.write((response+'\n').encode('utf-8'))
    
    writer.write(('DONE\n').encode('utf-8'))

# async client handler, for multiple connections
async def handle_client(reader, writer):
    """
    This is the method that receives the client's data and decides what to do
    with it. It runs in a loop to always be accepting new connections. If the
    data is 'status', the Lamp status is returned. If the data is 
    anything else, it is sent to handle_command().

    Inputs:
    - reader    from the asyncio library, to read incoming data
    - writer    from the asyncio library, to write outgoing data
    """

    request = None
    
    while request != 'quit':        
        request = (await reader.read(255)).decode('utf8')
        print(request.encode('utf8'))
        writer.write(('COMMAND = '+request.upper()).encode('utf8'))    

        args = request.split(' ')
        verb = args[0].lower()
        if verb == 'read':
            if len(args) == 2:
                obj = args[1].lower()

                if obj == 'lamp':
                    resp = get_lamp_status()

                elif obj == 'laser':
                    resp = get_laser_status()

                elif obj == 'lm_fault':
                    resp = get_lamp_fault()

                elif obj == 'c_fault':
                    resp = get_controller_status()

                else:
                    resp = 'BAD: \'read\' argument must be one of the following = \'lamp\', \'laser\', \'lm_fault\', \'c_fault\''
            else:
                resp = 'BAD: \'read\' command requires 1 argument'

        elif verb == 'set': 
            if len(args) == 3:
                obj = args[1].lower()
                val = args[2].lower()

                if obj == 'lamp':
                    if val == 'on':
                        resp = set_lamp(1)
                    elif val == 'off':
                        resp = set_lamp(0)
                    else:
                        resp = 'BAD: \'set\' argument 2 must be one of the following = \'on\', \'off\''

                elif obj == 'interlock':
                    if val == 'on':
                        resp = set_interlock(1)
                    elif val == 'off':
                        resp = set_interlock(0)
                    else:
                        resp = 'BAD: \'set\' argument 2 must be one of the following = \'on\', \'off\''
                else:
                    resp = 'BAD: \'set\' argument 1 must be one of the following = \'lamp\', \'interlock\''
            else:
                resp = 'BAD: \'set\' command requires 2 arguments'
        else:
            resp = resp + '\n'
            writer.write(resp.encode('utf8'))

        await writer.drain()
    writer.close()

async def main(HOST, PORT):
    print("Opening connection @"+HOST+":"+str(PORT))
    server = await asyncio.start_server(handle_client, HOST, PORT)
    await server.serve_forever()
    
if __name__ == "__main__":
    log = log_start()
    pi = pigpio.pi()
    initialize_gpio()

    # setup Remote TCP Server
    HOST, PORT = '', 9999

    try:
        asyncio.run(main(HOST,PORT))
    except KeyboardInterrupt:
        print('...Closing server...')
    except:
        print('Unknown error')
