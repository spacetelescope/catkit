### -- contains the target acq and calibration functions 

## -- IMPORTS
import config
import os

import numpy as np
from photuilts import centroid_1dg

## -- RUN

def accquire_target(camera1, camera2, pico, tiptilt, hole1=None, hole2=None):
    """Function to accquire the target well enough for nPoint to kick in.

    Parameters
    ----------
    
    camera1 : ZwoCamera object
        Connection to the pupil/TA camera.
    
    camera2 : ZwoCamera Objet
        Connection to the science/image camera.

    pico : NewportPicomotor object
        Connection to the picomotors. Assumes motors 1/2 and 3/4 will map to
        camera 1 and camera 2. 
    hole1 : tupel of ints
        The pixel location (x,y) of the hole for camera 1. Defaults to None.
    hole2 : tupel of ints
        the pixel locataion (x,y) of the hole for camera 2. Defaults to None.
    """
    
    # First pull hole location if not passed in
    if None in [hole1, hole2]:
        file_path = os.environ.get('CATKIT_CONFIG')
        
        config_path = os.environ.get('CATKIT_CONFIG')
        if config_path is None:
            raise OSError('No available config to specify picomotor connection.')
        
        config = configparser.ConfigParser()
        config.read(config_path)
            
        hole1 = config.get('target_acquisition', 'hole1') if hole1 is None else hole1
        hole2 = config.get('target_acquisition', 'hole2') if hole2 is None else hole2
    
    # Move camera 1 to hole
    tries = 0
    while not meets_threshold(camera1, threshold) or tries < 3: 
        img1_current = camera1.__capture(100)
        current_position = centroid_1dg(img1_current)
        for index, position in enumerate(current_position):
            # Calculate the command for x/y (axis 1/2)
            distance = hole1[index] - position
            axis = index+1
            r_ratio = pico.calibration['r_ratio_{}'.format(axis)]
            move = round(distance * 1/r_ratio)
            
            # Make the move
            pico.command('relative_move', axis, move)
    
    # Close the loop
    tiptilt.command('loop', 1, 1)
    tiptilt.command('loop', 2, 1)

    # Move camera 2 to hole
    tries = 0
    while not meets_threshold(camera1, threshold) or tries < 3:
        img2_current = camera2.__capture(100)
        curren_position = centroid_1dg(img2_current)
        for index, position in enumerate(current_position):
            # Calculate the command for x/y (axis 1/2)
            distance = hole1[index] - position
            axis = index+3
            r_ratio = pico.calibration['r_ratio_{}'.format(axis)]
            move = round(distance * 1/r_ratio)
            
            # Make the move
            pico.command('relative_move', axis, move)
    

def calibrate_motors(pico, cameras, move=50, exp_time=100):
    """ Function to calibrate motors to pixel distance. 

    Parameters
    ----------
    pico : NewportPicomotor object
        Connection to the picomotors. Assumes that picomotors will map 1/2 to
        camera1 and 3/4 to camera2
    cameras : list of ZwoCamera objects
        List of cameras to calibrate. 
        Connection to the science/imaging camera. 
    """
    if len(cameras) > 2:
        raise ValueError("We can only calibrate two cameras.")

    img = camera1.__capture(exp_time)
    for index, cam in enumerate(cameras):
        for n in (1,2):
            axis = 2*index + n
            pico.command('relative_move', axis, move)
            img_after = cam.__capture(exp_time)
            delta_theta = convert_move_to_pixel(self, img, img_after, move, axis)[-1]
            if np.abs(delta_theta) > .09:
                # some logging/print behavior
                print('Axis {} is more than 5 degrees off the intended x/y axis.'.format(axis))
            img = img_after


def find_hole(camera1, camera2, exp1, exp2):
    """ Finds the hole for each camera. 

    Parameters
    ----------
    camera1 : ZwoCamera object.
        Connection to the TA/pupil camera.
    camera2 : ZwoCamera object.
        Connection to the science/imaging camera.
    exp1 : int
        Length of the exposure time needed to centroid the first camera.
    exp2 : int
        Length of the exposure time needed to centroid the second camera.
    
    Returns
    -------
    hole1 : tupel of floats
        The (x,y) position of the dark hole for camera 1.
    hole2 : tupel of floats
        the (x,y) position of the dark hole for camera 2.
    """

    print('Please shine light into the front of the FPM.')
    input('Press any key when ready.')
    img = camera1.__capture(exp1)
    try:
        hole1 = centroid_1dg(img)
    except RunTimeError:
        # print/log behavior
        raise something from something. 
        print('A central point was not found for the image. Try repositioning or a higher exposure time.')
    img = camera2.__capture(exp2)
    try:
        hole2 = centrod_1dg(img)
    except RuntimeError:
        # print/log behavior

def meets_threshold(camera, threshold, exp_time=100):
    """ Checks if the image meets the threshold condition for through the hole.
     
    Parameters
    ----------
    camera : ZwoCamera object
        Connection to the camera.
    threshold : float
        The value below which we deem the target is not in the hole.
    exp_time : int, optional
        How long the image exposure should be. Defaults to 100 microseconds.
    Returns
    -------
    A boolean for whether or not the condition is met.
    """

    return sum(camera.__capture(exp_time)) >= threshold


def run_full_ta(camera1, camera2, pico, tiptilt, find_hole=False, calibrate=False):
    """ Main function to run a full TA iteration."""

    if find_hole:
        find_hole()
    if calibrate:
        calibrate_motors(pico, [camera1, camera2])
    if meets_threshold(camera1, threshold):
        accquire_target(camera1, camera2, pico, tiptilt)


