""" Script to calibrate the picomotor step to camera pixel."""

## -- IMPORTS
import configparser
import os
import time

from astropy.io import fits
import matplotlib.pyplot as plt
import numpy as np
from photutils import centroid_1dg

from interfaces import newport_interface, npoint_tiptilt, zwo_camera

## -- SET UP CONFIG

CONFIG_FILE_NAME = "config.ini"
OVERRIDE_FILE_NAME = "config_local.ini"

# potentially unused
def get_config_ini_path():
    """Build the path to the config file."""
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), CONFIG_FILE_NAME)


def load_config_ini():
    """Loads the config file."""
    # Locate where on disk this file is.
    code_directory = os.path.dirname(os.path.realpath(__file__))

    # Read config file once here.
    config = configparser.ConfigParser()
    config._interpolation = configparser.ExtendedInterpolation()

    # Check if there is a local override config file (which is ignored by git).
    local_override_path = os.path.join(code_directory, override_file_name)
    result = config.read(local_override_path)
    if not result:
        config.read(os.path.join(code_directory, config_file_name))
    return config

def calibrate_picomotors():
    """Main script to calibrate picomotors."""

    # Read in config
    CONFIG_INI = load_config_ini()

    #nPoint
    npoint_constants = {}
    npoint_constants['disable'] = CONFIG_INI.getboolean('nPoint', 'disable')
    for constant in ['p_gain1', 'd_gain1', 'i_gain1', 'p_gain2', 'd_gain2', 'i_gain2']:
        npoint_constants[consant] = CONFIG_INI.getfloat('nPoint', constant)

    # zwoCam
    zwo_constants = {}
    for constant in ['sci_cam_x', 'sci_cam_y', 'ta_cam_x', 'ta_cam_y', 'laser_source_power']:
        zwo_constants[constant] = CONFIG_INI.getfloat('Camera', constant)

    #Calculate exposure time
    if (laser_source_power == 200.0):
	exposure_time_sc = 8000
	exposure_time_ta = 300
	through_hole_threshold = 200
    elif (laser_source_power == 20.0):
	exposure_time_sc = 8000
	exposure_time_ta = 300
	through_hole_threshold = 200000
    else:
	exposure_time_sc = 8000
	exposure_time_ta = 300
	through_hole_threshold = 200
    
    # why do we do this?
    #save once...
    with open('config.ini','w') as configfile:
	CONFIG_INI.write(configfile)
	
    #creating controller object
    if not disable:
	npoint = npoint_tiptilt.nPoint_TipTilt()
	npoint.command("loop", 1, 0)
	npoint.command("loop", 2, 0)
    else:
	print("TIP/TILT IS DISABLED\n")

    #CALIBRATION
    print("Calibrating science camera picomotors...\n")
    print("Calibrating X...\n")
    try:
        # This should be read from config file instead?
	zwocam_tac = zwo_camera.ZWOCamera()
	zwocam_tac.open_camera("ZWO ASI290MM(1)")
	zwocam = zwo_camera.ZWOCamera()
	zwocam.open_camera("ZWO ASI290MM(2)") #Open by name
    # When I encounter this error in the wild I will put the real exception in there.
    except Exception as e:
        print(e)
	print("There is an issue with the cameras. Please unplug and plug them back in.\n")
    
    pico = newport_interface.NewportPicomotor()
    
    #X
    pre_image = zwocam.take_exposure(exp_time=exposure_time_sc)
    zwocam.plot_image(pre_image, output_name='test_image_precal.png')
    pico.command('relative_move',1,100)
    time.sleep(2)
    post_image = zwocam.take_exposure(exp_time=exposure_time_sc)
    print("Calculating pixel to picomotor step ratio...\n")
    pico.convert_move_to_pixel(pre_image,post_image, -100, 1)

    #Y
    print("Calibrating Y...\n")
    pre_image = zwocam.take_exposure(exp_time=exposure_time_sc)
    pico.command('relative_move',2,100)
    time.sleep(2)
    post_image = zwocam.take_exposure(exp_time=exposure_time_sc)
    zwocam.plot_image(post_image, output_name='test_image_postcal.png')
    print("Calculating pixel to picomotor step ratio...\n")
    pico.convert_move_to_pixel(pre_image,post_image, -100, 2)
    print("Calculated ratios and delta thetas:\n")
    print(pico.r_ratio_1)
    print(pico.r_ratio_2)
    print(pico.delta_theta_1)
    print(pico.delta_theta_2)
    CONFIG_INI.set('Picomotor', 'r_ratio_1', str(pico.r_ratio_1))
    CONFIG_INI.set('Picomotor', 'r_ratio_2', str(pico.r_ratio_2))

    #MOVE PICO MOTORS (SCIENCE CAMERA) ONE
    print("Aligning beam through hole (move 1 of 2)...\n")
    regular = zwocam.take_exposure(exp_time=exposure_time_sc)
    zwocam.plot_image(regular, output_name='test_image.png')
    
    try:
	# #Move picomotors accoringly...
	beam_x, beam_y = centroid_1dg(regular)
	print(beam_x)
	print(sci_cam_x)
	print(beam_y)
	print(sci_cam_y)
	#input("Waiting\n")
	pico.command('relative_move',1, -1*(beam_x-sci_cam_x)/pico.r_ratio_1)
	time.sleep(2)
	pico.command('relative_move',2, -1*(beam_y-sci_cam_y)/pico.r_ratio_2)
	time.sleep(2)
	regular2 = zwocam.take_exposure(exp_time=exposure_time_sc)
	zwocam.plot_image(regular2, output_name='test_image_after.png')
    
    # This is gonna be the runtime centroid exception maybe?
    except Exception as e:
        print(e)
	print("An error has occured. Is the beam on the science camera?\n")


    regular = zwocam_tac.take_exposure(exp_time = exposure_time_ta)
    if np.sum(regular) > through_hole_threshold:
	print("Aligning beam through hole (move 2 of 2)...\n")
	regular = zwocam.take_exposure(exp_time=exposure_time_sc)
	zwocam.plot_image(regular, output_name='test_image2.png')
	# #Move picomotors accoringly...
	beam_x, beam_y = centroid_1dg(regular)
	print(beam_x)
	print(sci_cam_x)
	print(beam_y)
	print(sci_cam_y)
	pico.command('relative_move',1, -1*(beam_x-sci_cam_x)/pico.r_ratio_1)
	time.sleep(2)
	pico.command('relative_move',2, -1*(beam_y-sci_cam_y)/pico.r_ratio_2)
	time.sleep(2)
	regular2 = zwocam.take_exposure(exp_time = exposure_time_sc)
	zwocam.plot_image(regular2, output_name='test_image2_after.png')
    else:
	print("Beam is already through the hole.\n")




    #Close loop
    if not disable:
	input("Use picomotors to align the quadcell. Press enter when finished.")
	
	print("Closing loop two...\n")
	#input("Press enter to continue.")
	#Gain values
	time.sleep(2)
	
	npoint.command("p_gain",1, p_gain1)
	npoint.command("d_gain",1,d_gain1)
	npoint.command("i_gain",1, i_gain1)
	npoint.command("p_gain", 2, p_gain2)
	npoint.command("d_gain", 2, d_gain2)
	npoint.command("i_gain", 2, i_gain2)
	time.sleep(.5)
	npoint.command("loop",2,1)
	print("Loop two is closed. Closing loop one...\n")
	#input("Press enter to continue.")
	time.sleep(.5)
	npoint.command("loop",1,1)

	npoint.get_status(1)
	npoint.get_status(2)
	print("Both loops closed.\n")



    input("Press enter to continue.")
    time.sleep(2)


    #Move picomotors accoringly...
    pico = newport_interface.NewportPicomotor()
    #Calibration
    print("Calibrating target aquisition picomotors...")
    print("Calibrating X...\n")
    if disable:
	#X
	pre_image = zwocam_tac.take_exposure(exp_time=exposure_time_ta)
	pico.command('relative_move',1,100)
	time.sleep(2)
	post_image = zwocam_tac.take_exposure(exp_time=exposure_time_ta)
	print("Calculating pixel to picomotor step ratio...\n")
	pico.convert_move_to_pixel(pre_image,post_image, 100, 3)

	#Y
	print("Calibrating Y...\n")
	pre_image = zwocam_tac.take_exposure(exp_time=exposure_time_ta)
	pico.command('relative_move',2,100)
	time.sleep(2)
	post_image = zwocam_tac.take_exposure(exp_time=exposure_time_ta)
	print("Calculating pixel to picomotor step ratio...\n")
	pico.convert_move_to_pixel(pre_image,post_image, 100, 4)
    else:
	#X
	pre_image = zwocam_tac.take_exposure(exp_time=exposure_time_ta)
	pico.command('relative_move',3,100)
	time.sleep(2)
	post_image = zwocam_tac.take_exposure(exp_time=exposure_time_ta)
	print("Calculating pixel to picomotor step ratio...\n")
	pico.convert_move_to_pixel(pre_image,post_image, 100, 3)

	#Y
	print("Calibrating Y...\n")
	pre_image = zwocam_tac.take_exposure(exp_time=exposure_time_ta)
	pico.command('relative_move',4,100)
	time.sleep(2)
	post_image = zwocam_tac.take_exposure(exp_time=exposure_time_ta)
	print("Calculating pixel to picomotor step ratio...\n")
	pico.convert_move_to_pixel(pre_image,post_image, 100, 4)
    print("Calculated ratios and delta thetas:\n")
    print(pico.r_ratio_3)
    print(pico.r_ratio_4)
    print(pico.delta_theta_4)
    print(pico.delta_theta_3)
    CONFIG_INI.set('Picomotor', 'r_ratio_3', str(pico.r_ratio_3))
    CONFIG_INI.set('Picomotor', 'r_ratio_4', str(pico.r_ratio_4))
    r_ratio_3 = pico.r_ratio_3
    r_ratio_4 = pico.r_ratio_4


    #MOVE PICO MOTORS (TARGET AQUISITION CAMERA) 
    #Move picomotors accoringly...
    print("Performing precise centering...")
    image = zwocam_tac.take_exposure(exp_time=exposure_time_ta)
    #Save plots
    zwocam_tac.plot_image(image, output_name='image_TAC.png')
    beam_x, beam_y = centroid_1dg(image)
    print(beam_x)
    print(ta_cam_x)
    print(beam_y)
    print(ta_cam_y)
    input("Waiting\n")
    if not disable:
	pico.command('relative_move',3, -1*(beam_x-ta_cam_x)/r_ratio_3)
	time.sleep(2)
	pico.command('relative_move',4, -1*(beam_y-ta_cam_y)/r_ratio_4)
	time.sleep(2)
    else:
	pico.command('relative_move',1, 1*(beam_x-ta_cam_x)/r_ratio_3)
	time.sleep(2)
	pico.command('relative_move',2, 1*(beam_y-ta_cam_y)/r_ratio_4)
	time.sleep(2)
    
    # again why
    with open('config.ini','w') as configfile:
	CONFIG_INI.write(configfile)
	configfile.close()

    # not sure we need to wait here? 
    input("System complete. Press enter to exit...\n")
    npoint.close()
    pico.close()
    zwocam.close_out()
    zwocam_tac.close_out()


## -- run call

if __name__ == "__main__":
    calibrate_picomotors()
