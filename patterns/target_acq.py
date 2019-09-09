### -- contains the target acq and calibration functions 

## -- IMPORTS
import config
import os

from photuilts import centroid_1dg

from interfaces.newport_picomotor import NewportPicomotor
from interfaces.npoint_tiptilt import nPointTipTilt
# also cameras somehow?

## -- RUN

def accquire_target(camera1, camera2, pico, tiptilt, hole1=None, hole2=None):
    """Function to accquire the target well enough for nPoint to kick in.

    Parameters
    ----------
    
    camera1 : camera connection
    
    camera2 : camera connection

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
    while some_threshold or tries < 3: 
        img1_current = camera1.take_exposure?
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
    while some_threshold or tries < 3:
        img2_current = camera2.take_exposure?
        curren_position = centroid_1dg(img2_current)
        for index, position in enumerate(current_position):
            # Calculate the command for x/y (axis 1/2)
            distance = hole1[index] - position
            axis = index+3
            r_ratio = pico.calibration['r_ratio_{}'.format(axis)]
            move = round(distance * 1/r_ratio)
            
            # Make the move
            pico.command('relative_move', axis, move)
    

def calibrate_motors(pico, ):
    """ Function to calibrate motors

    # include warning if pico theta is too wild


def find_hole()


