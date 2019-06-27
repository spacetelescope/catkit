###IMPORTS
import configparser
import os
import time


from astropy.io import fits
import matplotlib.pyplot as plt
import numpy as np
from photutils import centroid_1dg
from photutils import centroid_2dg

from interfaces import zwo_camera

config_file_name = "config.ini"
override_file_name = "config_local.ini"

# unused
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

def locate_hole():
    """ Locate the hole for the FPM. """

    CONFIG_INI = load_config_ini()
	

    #Locate Holes
    zwocam_tac = zwo_camera.ZWOCamera()
    zwocam_tac.open_camera("ZWO ASI290MM(1)")
    zwocam = zwo_camera.ZWOCamera()
    zwocam.open_camera("ZWO ASI290MM(2)")

    print("\nShine a light into the back of the FPM.\n")
    input("Press enter when ready to take an image.\n")
    image = zwocam.take_exposure(exp_time=30000)
    zwocam.plot_image(image, output_name='sci_cam_hole.png')
    sci_cam_x, sci_cam_y = centroid_1dg(image)
    print(sci_cam_x)
    print(sci_cam_y)
    CONFIG_INI.set('Camera', 'sci_cam_x', str(sci_cam_x))
    CONFIG_INI.set('Camera', 'sci_cam_y', str(sci_cam_y))


    print("\nShine a light into the front of the FPM.\n")
    input("Press enter when ready to take an image.\n")
    image2 = zwocam_tac.take_exposure(exp_time=10000)
    zwocam_tac.plot_image(image2, output_name='ta_cam_hole.png')
    ta_cam_x, ta_cam_y = centroid_2dg(image2)
    print(ta_cam_x)
    print(ta_cam_y)
    CONFIG_INI.set('Camera', 'ta_cam_x',str(ta_cam_x))
    CONFIG_INI.set('Camera', 'ta_cam_y', str(ta_cam_y))


    with open('config.ini','w') as configfile:
	CONFIG_INI.write(configfile)
	configfile.close()

    zwocam_tac.close()
    zwocam.close()
    print("Hole locations saved to config file.\n")

## -- RUN
if __name__ == "__main__":
    locate_hole()

