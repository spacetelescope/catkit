###IMPORTS
#Config imports
from __future__ import (absolute_import, division, unicode_literals)
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

### SET Constants
CONFIG_INI = load_config_ini()

### GET Constants
#nPoint
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

#Save once...
with open('config.ini','w') as configfile:
	CONFIG_INI.write(configfile)
	
###Creating controller object
if not disable:
	global ctrl
	ctrl = controller_interface.Controller()
	ctrl.command("loop", 1, 0)
	ctrl.command("loop", 2, 0)
else:
	print("TIP/TILT IS DISABLED\n")

# ###CALIBRATION
print("Calibrating science camera picomotors...\n")
print("Calibrating X...\n")
zwo_cam_tac = ZWOCamera.ZWOCamera()
zwo_cam_tac.open_camera("ZWO ASI290MM(1)")
zwo_cam = ZWOCamera.ZWOCamera()
zwo_cam.open_camera("ZWO ASI290MM(2)") #Open by name
pm = newport_interface.NewportPicomotor()
#X
pre_image = zwo_cam.take_exposure(exp_time=100)
zwo_cam.plot_image(pre_image, output_name='test_image_precal.png')
pm.command('relative_move',1,100)
time.sleep(2)
post_image = zwo_cam.take_exposure(exp_time=100)
pm.convert_move_to_pixel(pre_image,post_image, -100, 1)

#Y
print("Calibrating Y...\n")
pre_image = zwo_cam.take_exposure(exp_time=100)
pm.command('relative_move',2,100)
time.sleep(2)
post_image = zwo_cam.take_exposure(exp_time=100)
zwo_cam.plot_image(post_image, output_name='test_image_postcal.png')
beam_x, beam_y = centroid_1dg(post_image)
print(beam_x)
print(sci_cam_x)
print(beam_y)
print(sci_cam_y)
input("Waiting\n")
pm.convert_move_to_pixel(pre_image,post_image, -100, 2)
print(pm.r_ratio_1)
print(pm.r_ratio_2)
print(pm.delta_theta_1)
print(pm.delta_theta_2)
#CONFIG_INI.add_section('Picomotor')
CONFIG_INI.set('Picomotor', 'r_ratio_1', str(pm.r_ratio_1))
CONFIG_INI.set('Picomotor', 'r_ratio_2', str(pm.r_ratio_2))




# ##MOVE PICO MOTORS (SCIENCE CAMERA) ONE
print("Aligning beam through hole (move 1 of 2)...\n")
regular = zwo_cam.take_exposure(exp_time=100)
zwo_cam.plot_image(regular, output_name='test_image.png')
# #Move picomotors accoringly...
beam_x, beam_y = centroid_1dg(regular)
print(beam_x)
print(sci_cam_x)
print(beam_y)
print(sci_cam_y)
input("Waiting\n")
pm.command('relative_move',1, -1*(beam_x-sci_cam_x)/pm.r_ratio_1)
time.sleep(2)
pm.command('relative_move',2, -1*(beam_y-sci_cam_y)/pm.r_ratio_2)
time.sleep(2)
regular2 = zwo_cam.take_exposure()
zwo_cam.plot_image(regular2, output_name='test_image_after.png')




# ##MOVE PICO MOTORS (SCIENCE CAMERA) TWO
regular = zwo_cam_tac.take_exposure(exp_time = 100)
if np.sum(regular) < 2000:
	print("Aligning beam through hole (move 3 of 2)...\n")
	regular = zwo_cam.take_exposure(exp_time=100)
	zwo_cam.plot_image(regular, output_name='test_image2.png')
	# #Move picomotors accoringly...
	beam_x, beam_y = centroid_1dg(regular)
	print(beam_x)
	print(sci_cam_x)
	print(beam_y)
	print(sci_cam_y)
	input("Waiting\n")
	pm.command('relative_move',1, -1*(beam_x-sci_cam_x)/pm.r_ratio_1)
	time.sleep(2)
	pm.command('relative_move',2, -1*(beam_y-sci_cam_y)/pm.r_ratio_2)
	time.sleep(2)
	regular2 = zwo_cam.take_exposure(exp_time = 800)
	zwo_cam.plot_image(regular2, output_name='test_image2_after.png')
else:
	print("Beam is already through the hole.\n")



###CLOSE THE LOOP
#Close loop
if not disable:
	input("Use picomotors to align the quadcell. Press enter when finished.")
	
	print("Closing loop two...\n")
	#input("Press enter to continue.")
	#Gain values
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
#Calibration
print("Calibrating target aquisition picomotors...")
print("Calibrating X...\n")

if disable:
	#X
	pre_image = zwo_cam_tac.take_exposure(exp_time=600)
	pm.command('relative_move',1,100)
	time.sleep(2)
	post_image = zwo_cam_tac.take_exposure(exp_time=600)
	pm.convert_move_to_pixel(pre_image,post_image, 100, 3)

	#Y
	print("Calibrating Y...\n")
	pre_image = zwo_cam_tac.take_exposure(exp_time=600)
	pm.command('relative_move',2,100)
	time.sleep(2)
	post_image = zwo_cam_tac.take_exposure(exp_time=600)
	pm.convert_move_to_pixel(pre_image,post_image, 100, 4)
else:
	#X
	pre_image = zwo_cam_tac.take_exposure(exp_time=600)
	pm.command('relative_move',3,100)
	time.sleep(2)
	post_image = zwo_cam_tac.take_exposure(exp_time=600)
	pm.convert_move_to_pixel(pre_image,post_image, 100, 3)

	#Y
	print("Calibrating Y...\n")
	pre_image = zwo_cam_tac.take_exposure(exp_time=600)
	pm.command('relative_move',4,100)
	time.sleep(2)
	post_image = zwo_cam_tac.take_exposure(exp_time=600)
	pm.convert_move_to_pixel(pre_image,post_image, 100, 4)

print(pm.r_ratio_3)
print(pm.r_ratio_4)
print(pm.delta_theta_4)
print(pm.delta_theta_3)
CONFIG_INI.set('Picomotor', 'r_ratio_3', str(pm.r_ratio_3))
CONFIG_INI.set('Picomotor', 'r_ratio_4', str(pm.r_ratio_4))
r_ratio_3 = pm.r_ratio_3
r_ratio_4 = pm.r_ratio_4


# ##MOVE PICO MOTORS (TARGET AQUISITION CAMERA) 
# #Move picomotors accoringly...
print("Performing precise centering...")
image = zwo_cam_tac.take_exposure(exp_time=600)
#Save plots
zwo_cam_tac.plot_image(image, output_name='image_TAC.png')
beam_x, beam_y = centroid_1dg(image)
print(beam_x)
print(ta_cam_x)
print(beam_y)
print(ta_cam_y)
input("Waiting\n")
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


with open('config.ini','w') as configfile:
	CONFIG_INI.write(configfile)
	configfile.close()


input("System complete. Press enter to exit...\n")
ctrl.command("loop", 2, 0)
ctrl.command("loop", 1, 0)
