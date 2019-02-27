## -- IMPORTS 
import datetime
import logging
import os

import matplotlib.pyplot as plt
import numpy as np
import pint

import zwoasi

## -- CLASSES AND FUNCTIONS

def zwo_except(function):
    """Decorator that catches ZWO errors."""

    @functools.wraps(function)
    def wrapper(self, *args, **kwargs):
        try:
            return function(self, *args, **kwargs)
        except (zwo.ZWO_Error, zwo.ZWO_IOError, zwo.ZWO_CaptureError) as e:
            self.logger.error("There's a ZWO-specific error.")
            self.logger.error(e)
            raise e

class ZWOCamera:
    """Class for the ZWOCamera. """
    
    def __init__(self):
        """ Init function to set up logging and instantiate the camera."""

        # Logging
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        log_file = os.path.join('.', 'zwo_camera_log_{}.txt'.format(
                                str(datetime.datetime.now()).replace(' ', '_').replace(':', '_')))
        fh = logging.FileHandler(filename=log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        ch = logging.StreamHandler()

        self.logger.info('Camera instantiated, and logging online.')
        
        # Camera set up
        # First see if the lib is already instantiated
        try:
            zwoasi.get_num_cameras()
        
        # If it isn't, read in the library file
        except AttributeError:
            cam_lib_file = 'libraries/ASICamera2.dll'
            zwoasi.init(cam_lib_file)
        
        # Unforseen complications.
        except Exception as e:
            logger.error(e)
            raise e
        
        # And then open the camera connection
        # THIS IS NOT GREAT! THIS WILL OPEN WHATEVER CAMERA IS FIRST IN LINE
        # This should be set to only select the camera name with :
        # camera_name = 'ZWO ...'
        # camera_index = zwoasi.list_cameras().index(camera_name)
        # zwoasi.Camera(camera_index)
        # However, until we decide with certainty which camera (or cameras)
        # we're using I don't see what else to do.
        self.camera = zwoasi.Camera(0)
                
    
    def __del__(self):
        """Destructor to specify close behavior."""
        self.close_out()

    def __enter__(self):
        """ Enter function to allow for context management."""
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        """ Exit function to allow for context management. In this case, closes
        the camera."""
        self.close_out()
    
    @zwo_except
    def take_exposure(self, exp_time=1000, output_name='camera_test.png'):
        """ Quick function to take a single exposure and write it to the given
        name. 

        Parameters
        ----------
        exp_time : int, optinal
            Exposure time for the image in microseconds. Defaults to 1000.
        output_name : str, optional
            What to name the plot out; defaults to "camera_test.png".
        
        Returns
        -------
        image : np.array
            Np.array of image data.
        """

        # Set up units
        units = pint.UnitRegistry()
        quantity = units.Quantity
 
        # Set up exposure and poll time with units.
        exposure_time = quantity(exp_time, units.microseconds)
        # This one helps to avoid the camera from crashing or something?
        poll = quantity(0.1, units.seconds)
        
        # Take the image
        image = self.camera.capture(
                    initial_sleep=exposure_time.to(units.seconds).magnitude,
                    poll=poll.magnitude)
 
        # Save it
        v_min = np.median(image) - 3*np.std(image)
        v_max = np.median(image) + 3*np.std(image)
        plt.imshow(image, vmin=v_min, vmax=v_max, cmap='gray')
        plt.colorbar()
        plt.savefig(output_name)
        plt.clf()
        self.logger.info('Image saved to {}.'.format(output_name))
        
        return image
    
    @zwo_except
    def close_camera(self):
        """Closes the camera."""
        
        self.camera.close()
        self.logger.info('Camera connection closed.')
    
    def close_logger(self):
        """ Closes the logging."""

        handlers = self.logger.handlers[:]
        for handler in handlers:
            handler.close()
            self.logger.removeHandler(handler)
    
    def close_out(self):
        """ Closes camera and shuts down logging if you didn't use context managers."""

        self.close_camera()
        self.close_logging()

# MAIN with ex
if __name__ == "__main__":
    with zwo_cam as ZWOCamera():
        zwo_cam.take_exposure()
        zwo_cam.take_exposure(exp_time=10000, output_name='brighter_image.png')
        zwo_cam.take_exposure(exp_time=100, output_name='fainter_image.png')

