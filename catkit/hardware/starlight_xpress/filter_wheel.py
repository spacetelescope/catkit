#!/usr/bin/python3
# sx_filter_server.py
# 5/13/2021
# Aidan Gray
# aidan.gray@idg.jhu.edu
# 
# This is an IndiClient for controlling the STUF Project's SX Filter Wheel.

import asyncio
import PyIndi
import time
import sys
import os
import threading
import logging
import subprocess
import numpy as np
from astropy.io import fits
from datetime import datetime

class IndiClient(PyIndi.BaseClient):
    def __init__(self):
        super(IndiClient, self).__init__()
    def newDevice(self, d):
        pass
    def newProperty(self, p):
        pass
    def removeProperty(self, p):
        pass
    def newSwitch(self, svp):
        pass
    def newNumber(self, nvp):
        pass
    def newText(self, tvp):
        pass
    def newLight(self, lvp):
        pass
    def newMessage(self, d, m):
        pass
    def serverConnected(self):
        pass
    def serverDisconnected(self, code):
        pass

def log_start():
    """
    Create a logfile that the rest of the script can write to.

    Output:
    - log 	Object used to access write abilities
    """

    scriptDir = os.path.dirname(os.path.abspath(__file__))
    scriptName = os.path.splitext(os.path.basename(__file__))[0]
    log = logging.getLogger('filter_server')
    hdlr = logging.FileHandler(scriptDir+'/logs/'+scriptName+'.log')
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    hdlr.setFormatter(formatter)
    log.addHandler(hdlr)
    log.setLevel(logging.INFO)
    return log
    
def connect_to_indi():
    """
    Establish a TCP connection to the indiserver via port 7624

    Output:
    - indiclient 	Object used to connect to the device properties
    """
    # Ensure the indiserver is running
    indiclient=IndiClient()
    indiclient.setServer("localhost",7624)
     
    if (not(indiclient.connectServer())):
         print("No indiserver running on "+indiclient.getHost()+":"+str(indiclient.getPort())+" - Try to run")
         print("  indiserver indi_sx_ccd indi_sx_wheel")
         sys.exit(1)

    return indiclient

def connect_to_wheel():
    """
    Connection routine for the Filter Wheel (given below in filter variable).
    The following Filter Wheel properties are accessed. More can be found
    by going to indilib.org.
    - CONNECTION 			Switch
    - FILTER_SLOT 			Number
    - FILTER_NAME			Text

    Inputs:
    - NONE

    Outputs:
    - filter_slot 	
    - filter_name	
    """

    filter="SX Wheel"
    device_filter=indiclient.getDevice(filter)
    while not(device_filter):
        time.sleep(0.5)
        device_filter=indiclient.getDevice(filter)
        print("Searching for device...")

    print("Found indiserver device")
    time.sleep(0.5)
    # connect to the filter wheel device
    filter_connect=device_filter.getSwitch("CONNECTION")
    while not(filter_connect):
        time.sleep(0.5)
        filter_connect=device_filter.getSwitch("CONNECTION")
    if not(device_filter.isConnected()):
        filter_connect[0].s=PyIndi.ISS_ON  # the "CONNECT" switch
        filter_connect[1].s=PyIndi.ISS_OFF # the "DISCONNECT" switch
        indiclient.sendNewSwitch(filter_connect)
 
 	# get the current slot number
    filter_slot=device_filter.getNumber("FILTER_SLOT")
    n = 0.0
    while not(filter_slot):
        time.sleep(0.5)
        filter_slot=device_filter.getNumber("FILTER_SLOT")
        n+=0.5
        if n == TIMEOUT:
            sys.exit("ERROR: Failed to initialize device")
        

    # get the current slot name
    filter_name=device_filter.getText("FILTER_NAME")
    while not(filter_name):
    	time.sleep(0.5)
    	filter_name=device_filter.getText("FILTER_NAME")

    return filter_slot, filter_name

def slotState():
    """
    Returns True if the wheel is busy moving
    Returns False if the wheel is idle
    """

    if filter_slot[0].value == cSLOT:
        return False
    else:
        return True

def setParams(commandList):
    """
    Changes filter wheel parameters/settings based on the given arguments

    Input:
    - commandList   a list of strings, each being a parameter to set

    Output:
    - response      the response, OK/BAD
    """

    response = ''
    global cSLOT

    for i in commandList:
        # set the filter slot
        if 'slot=' in i:
            try:
                slot = int(i.replace('slot=',''))
                if slot >= 1 and slot <= 5:
                    filter_slot[0].value = slot
                    cSLOT = slot
                    indiclient.sendNewNumber(filter_slot)
                    response = 'OK'
                else:
                    response = 'BAD: Invalid Filter Slot'
            except ValueError:
                response = 'BAD: Invalid Filter Slot'
                
        # set the slot name
        elif 'slotName=' in i:
            try:
                slotName = str(i.replace('slotName=',''))
                if len(slotName) <= 50:
                    #response = 'OK: Setting current filter name to '+slotName
                    filter_name[int(filter_slot[0].value)-1].text = slotName
                    indiclient.sendNewText(filter_name)
                    response = 'OK'
                else:
                    response = 'BAD: Invalid filter name'
            except ValueError:
                response = 'BAD: Invalid filter name'

        else:
            response = 'BAD: Invalid Set'+'\n'+response

    return response

def handle_command(log, writer, data): 
    """
    Determines what to do with the incoming data - setting a parameter. 
    This is a separate method from handle_client() because it is called 
    as a new thread, so ensure the exposure is non-blocking.

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
    
    time.sleep(0.1)
    while slotState():
        time.sleep(0.1)
    
    writer.write(('DONE\n').encode('utf-8'))

# async client handler, for multiple connections
async def handle_client(reader, writer):
    """
    This is the method that receives the client's data and decides what to do
    with it. It runs in a loop to always be accepting new connections. If the
    data is 'status', the Filter Wheel status is returned. If the data is 
    anything else, a new thread is created and the data is sent to handle_command().

    Inputs:
    - reader    from the asyncio library, to read incoming data
    - writer    from the asyncio library, to write outgoing data
    """

    request = None
    
    while request != 'quit':        
        request = (await reader.read(255)).decode('utf8')
        print(request.encode('utf8'))
        #log.info('COMMAND = '+request)
        writer.write(('COMMAND = '+request.upper()).encode('utf8'))    

        response = 'BAD'
        # check if data is empty, a status query, or potential command
        dataDec = request
        if dataDec == '':
            break
        elif 'status' in dataDec.lower():
            response = 'OK'
            if slotState():
                response = response + '\nBUSY'
            else:
                response = response + '\nIDLE'

            response = response+\
                '\nSLOT# = '+str(filter_slot[0].value)+\
                '\nSLOTNAME = '+str(filter_name[int(filter_slot[0].value)-1].text)

            # send current status to open connection & log it
            #log.info('RESPONSE: '+response)
            writer.write((response+'\nDONE\n').encode('utf-8'))
        else:
            # check if the command thread is running, may fail if not created yet, hence try/except
            try:
                if slotState():
                    response = 'BAD: BUSY'
                    # send current status to open connection & log it
                    #log.info('RESPONSE = '+response)
                    writer.write((response+'\nDONE\n').encode('utf-8'))
                else:
                    # create a new thread for the command
                    comThread = threading.Thread(target=handle_command, args=(log, writer, dataDec,))
                    comThread.start()
            except:
                # create a new thread for the command
                comThread = threading.Thread(target=handle_command, args=(log, writer, dataDec,))
                comThread.start()

        await writer.drain()
    writer.close()

async def main(HOST, PORT):
    print("Opening connection @"+HOST+":"+str(PORT))
    server = await asyncio.start_server(handle_client, HOST, PORT)
    await server.serve_forever()
    
if __name__ == "__main__":
    TIMEOUT = 5.0
    log = log_start()
    
    # connect to the local indiserver
    indiclient = connect_to_indi()
    filter_slot, filter_name = connect_to_wheel()
    
    # setup Remote TCP Server
    HOST, PORT = '', 9998

    cSLOT = 1 # GLOBAL VAR for keeping track of COMMANDED slot, for checking busy/idle state
    filter_slot[0].value = 1 # Initialize the filter wheel to slot 1 on startup
    indiclient.sendNewNumber(filter_slot)

    try:
        asyncio.run(main(HOST,PORT))
    except KeyboardInterrupt:
        print('...Closing server...')
    except:
        print('Unknown error')
