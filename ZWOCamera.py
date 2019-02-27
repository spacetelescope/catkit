## -- IMPORTS 
import datetime
import logging
import os

import matplotlib.pyplot as plt
import numpy as np
import pint

import zwoasi

## -- CLASS DEFINITION

class ZWOCamera:
    """Class for the ZWOCamera. """
    
    def __init__(self):
        """ Init function to set up logging and instantiate the camera."""

        # Camera set up
        # First see if the lib is already instantiated
        try:
            zwoasi.get_num_cameras()
        
        # If it isn't, read in the library file
        except AttributeError:
            cam_lib_file = 'C:/Users/RMOLStation1s/piezo_tiptilt/hicat-package/hicat/hardware/zwo/lib/windows/ASICamera2.dll'
            zwoasi.init(cam_lib_file)
        
        # Unforseen complications.
        except Exception:
            raise
        
        # And then open the camera connection
        self.camera = zwoasi.Camera(0)
        
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


    def __enter__(self):
        """ Enter function to allow for context management."""
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        """ Exit function to allow for context management. In this case, closes
        the camera."""
        self.camera.close()

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
        print('Image saved to {}.'.format(output_name))
        
        return image

    def close_camera(self):
        """Closes the camera if you didn't use context managers."""
        self.camera.close()


