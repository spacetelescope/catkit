###IMPORTS
#Config file imports
from __future__ import (absolute_import, division,
                        unicode_literals)

from builtins import *
import configparser
import os

#Camera imports
import ZWOCamera

#Controller imports
import controller_interface

#Picomotor imports
import newport_interface

#Centroid imports
from astropy.io import fits
import matplotlib.pyplot as plt
import numpy as np
from photutils import centroid_1dg
import time
import subprocess
import sys

config_file_name = "config.ini"
override_file_name = "config_local.ini"

def get_config_ini_path():
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), config_file_name)


def load_config_ini():
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


def mainLoop(firstTime):
	# ##MOVE PICO MOTORS (SCIENCE CAMERA) ONE
	pm = newport_interface.NewportPicomotor()
	image = zwo_cam_tac.take_exposure(exp_time=800)
	beam_x, beam_y = centroid_1dg(image)
	if np.sum(image) < threshold:
		print("Aligning beam through hole (move 1 of 2)...\n")
		regular = zwo_cam.take_exposure(exp_time=800)
		zwo_cam.plot_image(regular, output_name='test_image.png')
		# #Move picomotors accoringly...
		beam_x, beam_y = centroid_1dg(regular)
		pm.command('relative_move',1, -1*(beam_x-sci_cam_x)/r_ratio_1)
		time.sleep(2)
		pm.command('relative_move',2, -1*(beam_y-sci_cam_y)/r_ratio_2)
		time.sleep(2)
		regular2 = zwo_cam.take_exposure(exp_time = 800)
		zwo_cam.plot_image(regular2, output_name='test_image_after.png')
	else:
		print("Beam is already through the hole.\n")



	# # ##MOVE PICO MOTORS (SCIENCE CAMERA) TWO
	# print("Aligning beam through hole (move 2 of 2)...\n")
	# regular = zwo_cam.take_exposure()
	# zwo_cam.plot_image(regular, output_name='test_image2.png')
	# # #Move picomotors accoringly...
	# beam_x, beam_y = centroid_1dg(regular)
	# pm.command('relative_move',1, -1*(beam_x-sci_cam_x)/r_ratio_1)
	# time.sleep(2)
	# pm.command('relative_move',2, -1*(beam_y-sci_cam_y)/r_ratio_2)
	# time.sleep(2)
	# regular2 = zwo_cam.take_exposure()
	# zwo_cam.plot_image(regular2, output_name='test_image2_after.png')



	###CLOSE THE LOOP
	#Close loop
	if not disable:
		if firstTime:
			input("Use picomotors to align the quadcell. Press enter when finished.")
			
		print("Closing loop two...\n")
		time.sleep(2)
		ctrl.command("p_gain",1, p_gain1)
		ctrl.command("d_gain",1,d_gain1)
		ctrl.command("i_gain",1, i_gain1)
		ctrl.command("p_gain", 2, p_gain2)
		ctrl.command("d_gain", 2, d_gain2)
		ctrl.command("i_gain", 2, i_gain2)
		time.sleep(.5)
		ctrl.command("loop",2,1)
		print("Loop two is closed. Closing loop one...\n")
		#input("Press enter to continue.")
		time.sleep(.5)
		ctrl.command("loop",1,1)

		ctrl.get_status(1)
		ctrl.get_status(2)
		print("Both loops closed.\n")


	#input("Press enter to continue.")

	time.sleep(2)


	# ##MOVE PICO MOTORS (TARGET AQUISITION CAMERA) 
	# #Move picomotors accoringly...
	pm = newport_interface.NewportPicomotor()
	print("Performing precise centering...")
	image = zwo_cam_tac.take_exposure(exp_time=800)
	#Save plots
	zwo_cam_tac.plot_image(image, output_name='image_TAC.png')
	beam_x, beam_y = centroid_1dg(image)
	if not disable:
		pm.command('relative_move',3, -1*(beam_x-ta_cam_x)/r_ratio_3)
		time.sleep(2)
		pm.command('relative_move',4, -1*(beam_y-ta_cam_y)/r_ratio_4)
		time.sleep(2)
	else:
		pm.command('relative_move',1, 1*(beam_x-ta_cam_x)/r_ratio_3)
		time.sleep(2)
		pm.command('relative_move',2, 1*(beam_y-ta_cam_y)/r_ratio_4)
		time.sleep(2)

	print("System complete. The laser is perfectly centered through the hole.")
	print("Ensuring laser is through the hole (checking every 5 seconds).")
	image = zwo_cam_tac.take_exposure(exp_time=800)
	old_beam_x, old_beam_y = centroid_1dg(image)
	while(True):
		time.sleep(5)
		image = zwo_cam_tac.take_exposure(exp_time=800)
		beam_x, beam_y = centroid_1dg(image)
		if ((np.abs(old_beam_x - beam_x) > 20) or (np.abs(old_beam_y - beam_y) > 20)):
			print("Beam has moved. Restarting alignment process.")
			#Restart program
			break
		if np.sum(image) < threshold:
			print("Loop is broken. Restarting alignment process.")
			#Restart program
			break
		old_beam_x = beam_x
		old_beam_y = beam_y	
	
	
	
###Constants
threshold = 2000
CONFIG_INI = load_config_ini()
disable = CONFIG_INI.getboolean('nPoint', 'disable')
p_gain1 = CONFIG_INI.getfloat('nPoint', 'p_gain1')
d_gain1 = CONFIG_INI.getfloat('nPoint', 'd_gain1')
i_gain1 = CONFIG_INI.getfloat('nPoint', 'i_gain1')
p_gain2 = CONFIG_INI.getfloat('nPoint', 'p_gain2')
d_gain2 = CONFIG_INI.getfloat('nPoint', 'd_gain2')
i_gain2 = CONFIG_INI.getfloat('nPoint', 'i_gain2')
#Camera
sci_cam_x = CONFIG_INI.getfloat('Camera', 'sci_cam_x')
sci_cam_y = CONFIG_INI.getfloat('Camera', 'sci_cam_y')
ta_cam_x = CONFIG_INI.getfloat('Camera', 'ta_cam_x')
ta_cam_y = CONFIG_INI.getfloat('Camera', 'ta_cam_y')
#Picomotor
r_ratio_1 = CONFIG_INI.getfloat('Picomotor', 'r_ratio_1')
r_ratio_2 = CONFIG_INI.getfloat('Picomotor', 'r_ratio_2')
r_ratio_3 = CONFIG_INI.getfloat('Picomotor', 'r_ratio_3')
r_ratio_4 = CONFIG_INI.getfloat('Picomotor', 'r_ratio_4')



###Creating controller object
if not disable:
	global ctrl
	ctrl = controller_interface.Controller()
	ctrl.command("loop", 1, 0)
	ctrl.command("loop", 2, 0)
else:
	print("TIP/TILT IS DISABLED\n")

# ###CALIBRATION
print("Loading calibration...\n")
zwo_cam_tac = ZWOCamera.ZWOCamera()
zwo_cam_tac.open_camera("ZWO ASI290MM(1)")
zwo_cam = ZWOCamera.ZWOCamera()
zwo_cam.open_camera("ZWO ASI290MM(2)") #Open by name

#Call main loop
firstTime = True
while True:
	mainLoop(firstTime)
	firstTime = False
	
	



