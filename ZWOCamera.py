## -- IMPORTS 
import datetime
import logging
import os

from astropy.io import fits
import matplotlib.pyplot as plt
import numpy as np
import pint

import zwoasi

## -- CLASSES AND FUNCTIONS
# Decorator with error handling.
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
    return wrapper


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
    def take_exposure(self, exp_time=1000):
        """ Quick function to take a single exposure.
        Parameters
        ----------
        exp_time : int, optinal
            Exposure time for the image in microseconds. Defaults to 1000.
        
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
 
        return image
    
    def write_out_image(self, image, output_name='images/camera_test.fits'):
        """ Writes out the camera image to a FITS file.

        Parameters
        ----------
        image : np.array
            Np.array image output from `take_exposure`.
        output_name : str, optional
            Name of the output image. Includes path. Defaults to
            'images/camera_test.fits'.
        
        Notes
        -----
        If you don't specify a name and you're taking multiple images you will
        overwrite them each time.
        """
        
        # Write a header
        hdr = fits.Header()
        hdr['WRITE-DATE'] = str(datetime.datetime.now())
        
        # Write out the file
        hdu = fits.PrimaryHDU(data=image, header=hdr)
        hdu.writeto(output_name)

    def plot_image(self, image, colors='gray', norm='3-std', output_name='images/camera_test.png'):
        """ Plots the camera image. 
        
        Parameters
        ----------
        image : np.array
            Np.array image output from `take_exposure`.
        colors : str, optional
            The colormap to plot it. Takes any `matplotlib.pyplot.imshow` colormap key. 
            Defaults to 'gray'.
        norm : str, optional
            Key for how the color scale should be normalized. Right now will take any
            key of the form 'x-std' (ex '3-std') for median +/- x stds, 'x,y'
            for x and y as the min and max of the image, 'min/max' for set to min and 
            max of the image, and None, for no normalization. Defaults to '3-std'.
        output_name, str, optional
            Name of the output image. Includes path. Defaults to
            'images/camera_test.png'
        """

        # Set the appropriate scale normalization
        if 'std' in norm:
            factor = norm.split('-')[0]
            if factor.isdigit():
                factor = int(factor)
                v_min = np.median(image) - factor*np.std(image)
                v_max = np.median(image) + factor*np.std(image)
            else:
                self.logger.warning("In order to use the 'x-std' normalization you need an int. Try '3-std'.")
                raise ValueError("In order to use the 'x-std' normalization you need an int. Try '3-std'.")
        
        elif ',' in norm:
            try:
                v_min = float(norm.split(',')[0])
                v_max = float(norm.split(',')[1])
            except ValueError:
                self.logger.warning("In order to use the 'x,y' normalization you need two numbers. Try '-2.1,400'")
                raise ValueError("In order to use the 'x,y' normalization you need two numbers. Try '-2.1,400'")
        
        elif norm == 'min/max':
            v_min = np.min(image)
            v_max = np.max(image)

        elif norm == None:
            v_min, v_max = None, None

        else:
            self.logger.warning("The normalization scheme you tried doesn't exist.")
            raise NotImplementedError("The normalization scheme you tried doesn't exist.")

        # Save it
        plt.imshow(image, vmin=v_min, vmax=v_max, cmap=colors)
        plt.colorbar()
        plt.savefig(output_name)
        plt.clf()
        self.logger.info('Image saved to {}.'.format(output_name))
        
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
        """ Closes camera and shuts down logging if you didn't use context managers.
        Note that this is named `close_out` and not close because the
        zwoasi.Camera object also has a close method and I'm trying not to
        overload it."""

        self.close_camera()
        self.close_logger()

# MAIN with ex
if __name__ == "__main__":
    with zwo_cam as ZWOCamera():
        regular = zwo_cam.take_exposure()
        bright = zwo_cam.take_exposure(exp_time=10000)
        faint = zwo_cam.take_exposure(exp_time=100)
        
        zwo_cam.plot_image(regular, output_name='regular_image.png')
        zwo_cam.plot_image(bright, output_name='bright_image.png')
        zwo_cam.plot_image(faint, output_name='faint_image.png')
