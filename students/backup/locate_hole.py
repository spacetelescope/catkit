###IMPORTS
#Config imports
from __future__ import (absolute_import, division, unicode_literals)
from builtins import *
import configparser
import os

#Camera imports
import ZWOCamera

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
	

#Locate Holes
zwo_cam_tac = ZWOCamera.ZWOCamera()
zwo_cam_tac.open_camera("ZWO ASI290MM(1)")
zwo_cam = ZWOCamera.ZWOCamera()
zwo_cam.open_camera("ZWO ASI290MM(2)")

print("\nShine a light into the back of the FPM.\n")
input("Press enter when ready to take an image.\n")
image = zwo_cam.take_exposure(exp_time=30000)
zwo_cam.plot_image(image, output_name='sci_cam_hole.png')
sci_cam_x, sci_cam_y = centroid_1dg(image)
print(sci_cam_x)
print(sci_cam_y)
CONFIG_INI.set('Camera', 'sci_cam_x', str(sci_cam_x))
CONFIG_INI.set('Camera', 'sci_cam_y', str(sci_cam_y))


print("\nShine a light into the front of the FPM.\n")
input("Press enter when ready to take an image.\n")
image = zwo_cam_tac.take_exposure(exp_time=25000)
zwo_cam_tac.plot_image(image, output_name='ta_cam_hole.png')
ta_cam_x, ta_cam_y = centroid_1dg(image)
print(ta_cam_x)
print(ta_cam_y)
CONFIG_INI.set('Camera', 'ta_cam_x',str(ta_cam_x))
CONFIG_INI.set('Camera', 'ta_cam_y', str(ta_cam_y))


with open('config.ini','w') as configfile:
	CONFIG_INI.write(configfile)
	configfile.close()

zwo_cam_tac.close()
zwo_cam.close()
print("Hole locations saved to config file.\n")