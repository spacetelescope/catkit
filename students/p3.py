###IMPORTS

import configparser
import os
import time
import sys

from astropy.io import fits
import matplotlib.pyplot as plt
import numpy as np
from photutils import centroid_1dg

from interfaces import newport_interface, npoint_tiptilt, zwo_camera

CONFIG_FILE_NAME = "config.ini"
OVERRIDE_FILE_NAME = "config_local.ini"

#Returns true if beam is through the hole and cenetered, false otherwise
def check_beam(cam, cam_tac):
    """ Checks if beam is through the hole. Returns True/False. """

    time.sleep(time_between_beam_checking)
    image = cam_tac.take_exposure(exp_time=exposure_time_ta)
    beam_x, beam_y = centroid_1dg(image)
    print(np.sum(image))
    
    if ((np.abs(ta_cam_x - beam_x) > misaligned_threshold).\
        or (np.abs(ta_cam_y - beam_y) > misaligned_threshold)):
        print("Beam has moved. Restarting alignment process.")
        #Restart program
        return False
    
    elif np.sum(image) < through_hole_threshold:
        print("Loop is broken. Restarting alignment process.")
        #Restart program
        return False
    
    else:
        return True

# unused
def get_config_ini_path():
    return os.path.join(os.path.dirname(os.path.realpath(__file__)),
            CONFIG_FILE_NAME)


def load_config_ini():
    # Locate where on disk this file is.
    code_directory = os.path.dirname(os.path.realpath(__file__))

    # Read config file once here.
    config = configparser.ConfigParser()
    config._interpolation = configparser.ExtendedInterpolation()

    # Check if there is a local override config file (which is ignored by git).
    local_override_path = os.path.join(code_directory, OVERRIDE_FILE_NAME)
    result = config.read(local_override_path)
    if not result:
        config.read(os.path.join(code_directory, CONFIG_FILE_NAME))
    return config


def main_close_loop(firstTime):
    """ Main function to close the loop. """
    
    # Load constants
    npoint_constants, zwo_constants, pico = load_config_constants()
    
    # Open interface connections

    # cameras 
    try:
        zwocam_tac = zwo_camera.ZWOCamera()
        zwocam_tac.open_camera("ZWO ASI290MM(1)")
        zwocam = zwo_camera.ZWOCamera()
        zwocam.open_camera("ZWO ASI290MM(2)") #Open by name
    except:
        print("There is an issue with the cameras. Please unplug and plug them back in.\n")

    # newport 
    pico = newport_interface.NewportPicomotor()
    
    # npoint 
    npoint = npoint_tiptilt.nPoint_TipTilt()
    
    # Round of moves to hole on the science camera
    move_to_hole(cameras=(zwocam, zwocam_tac), zwo_contants, pico_constants, mode='sience_cam')

    #Close loop
    if not disable:
        if firstTime:
            input("Use picomotors to align the quadcell. Press enter when finished.")
        
        print("Closing loop two...\n")
        close_tiptilt_loop(npoint, npoint_constants, 2)
        time.sleep(2)
        close_tiptilt_loop(npoint, npoint_constants, 1)
        print("Both loops closed...\n")

    # Move picomotors accoringly...
    print("Performing precise centering...")
    image = zwocam_tac.take_exposure(exp_time=zwo_constants['exposure_time_ta'])
    
    # Round of moves to hole on the TA camera
    if not disable:
        move_to_hole(cameras=(zwocam, zwocam_tac), zwo_constants, pico_constants, mode='ta_cam')

    print("System complete. The laser is perfectly centered through the hole.")
    print("Ensuring laser is through the hole (checking every 5 seconds).")
    while(check_beam(zwocam, zwocam_tac)):
        #Check beam indefinetly until it is broken or moves
        time.sleep(1)


def close_tiptilt_loop(npoint_instance, npoint_dict, channel):
    """ Closes tiptilt loop. 

    Parameters
    ----------
    npoint_instance : nPoint_TipTilt object
        Connection to npoint controller.
    npoint_dict : dict
        Dictionary of npoint config constants. 
    channel : int
        1, 2 -- which channel to close.
    """

    time.sleep(2)
    npoint.command("p_gain", channel, npoint_constants['p_gain'.format(channel)])
    npoint.command("d_gain", channel, npoint_constants['d_gain'.format(channel)])
    npoint.command("i_gain", channel, npoint_constants['i_gain'.format(channel)])
    time.sleep(.5)
    npoint.command("loop", channel, 1)

    npoint.get_status(channel)


def load_data_from_config():
    """ Loads data from config."""
    CONFIG_INI = load_config_ini()
    
    # nPoint
    npoint_constants = {}
    npoint_constants['disable'] = CONFIG_INI.getboolean('nPoint', 'disable')
    for constant in ['p_gain1', 'd_gain1', 'i_gain1', 'p_gain2', 'd_gain2', 'i_gain2']:
        npoint_constants[consant] = CONFIG_INI.getfloat('nPoint', constant)

    # zwoCam
    zwo_constants = {}
    for constant in ['sci_cam_x', 'sci_cam_y', 'ta_cam_x', 'ta_cam_y', 
                     'laser_source_power', 'misaligned_threshold',
                     'time_between_beam_checking', 'laser_source_power']:
        zwo_constants[constant] = CONFIG_INI.getfloat('Camera', constant)
    
    # Calculate exposure time
    zwo_constants['exposure_time_sc'] = 8000
    zwo_constants['exposure_time_ta'] = 300
    if zwo_constants['laser_source_power'] == 200.0:
        zwo_constants['through_hole_threshold'] = 15000
    else:
        zwo_constants['through_hole_threshold'] = 200

    # pico
    pico_constants = {}
    for constant in ['r_ratio_1', 'r_ratio_2', 'r_ratio_3', 'r_ratio_4']:
        pico_constants[constant] = CONFIG_INI.getfloat('Picomotor', constant)

    return npoint_constants, zwo_constants, pico_constants


def move_to_hole(cameras, zwo_dict, pico_dict, mode):
    """ Function to move cameras to the recorded hole location.

    Parameters
    ----------
    cameras : tup of ZWOCamera object
        Tuple with (science camera, tac camera).
    zwo_dict : dict
        Dictionary with zwo constants.
    pico_dict : dict
        Dictionary with picomotor constants.
    mode : str
        'science_cam' or 'ta_cam' for which camera hole to move to.
    """
    zwocam = cameras[0]
    zwocam_tac = cameras[1]

    if mode == 'science_cam':
        picture_cam = zwocam
        rx, ry = 'r_ratio_1', 'r_ratio_2'
        cam_key = 'sci_cam'
        niter = 0
    elif mode == 'ta_cam':
        picture_cam = zwocam_tac
        rx, ry = 'r_ratio_3', 'r_ratio_4'
        cam_key = 'ta_cam'
        # Only one iteration for TA
        niter = 4

    try:
        thresh_image = zwocam_tac.take_exposure(exp_time=zwo_dict['exposure_time_ta'])
        while np.sum(thresh_image) < zwo_dict['through_hole_threshold'] and niter <= 5:
            niter += 1
            print("Aligning beam through hole (move {} of 5)...\n".format(niter))
            #Move picomotors accoringly...
            image = picture_cam.take_exposure(exp_time=zwo_dict['exposure_time_sc'])
            beam_x, beam_y = centroid_1dg(image)
            pico.command('relative_move', int(rx[-1]), -1*(beam_x-zwo_dict['{}_x'.format(cam_key])/pico_dict[rx])
            time.sleep(2)
            pico.command('relative_move', int(ry[-1]), -1*(beam_y-zwo_dict['{}_y'.format(cam_key)])/pico_dict[ry])
            time.sleep(2)
            thresh_image = zwocam_tac.take_exposure(exp_time=zwo_dict['exposure_time_ta'])
        if niter == 5 and mode='sience_cam':
            # log? 
            print('5 moves was not enough to reach the threshold. Is the beam through the hole?') 

    except Exception as e:
        print(e)
        print("An error has occured. Is the beam on the camera?\n")



###Creating controller object
if not disable:
	npoint.command("loop", 1, 0)
	npoint.command("loop", 2, 0)
else:
	print("TIP/TILT IS DISABLED\n")

# ###CALIBRATION
## -- RUN

if __name__ == "__main__":
#Call main loop
firstTime = True
# UMMMM
while True:
    mainLoop(firstTime)
    firstTime = False
	

