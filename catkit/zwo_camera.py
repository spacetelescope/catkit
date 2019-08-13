## -- IMPORTS 
import datetime
import functools
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
        except (zwoasi.ZWO_Error, zwoasi.ZWO_IOError, zwoasi.ZWO_CaptureError) as e:
            raise Exception('{} : was caught do to a ZWO/camera specific error.'.format(e))
    return wrapper


class ZWOCamera:
    """Class for the ZWOCamera. """
    
    def __init__(self, camera='default'):
        """ Init function to set up logging and instantiate the camera
        libraries."""
        
        camera_library_file = os.environ.get("CAMERA_LIBRARY")
        if camera_library_file == None:
            raise FileNotFoundError("You need to export the 'CAMERA_LIBRARY' environment variable.")

        # Logging
        str_date = str(datetime.datetime.now()).replace(' ', '_').replace(':', '_')
        self.logger = logging.getLogger('ZWO_log_{}'.format(str_date))
        self.logger.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        log_file = 'zwo_camera_log_{}.log'.format(str_date)
        fh = logging.FileHandler(filename=log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        
        # Camera set up
        # First see if the lib is already instantiated
        try:
            zwoasi.get_num_cameras()
        
        # If it isn't, read in the library file
        except AttributeError:
            zwoasi.init(camera_library_file)
        
        # Unforseen complications.
        except Exception as e:
            raise e
        
        self.logger.info('Camera library instantiated and logging online.')
        
        if camera_name=='default':
            # Open first camera connection 
            self.camera = zwoasi.Camera(0)
            self.name = self.camera.get_camera_property()['Name']
        
        elif camera_name in zwoasi.list_cameras():
            # Set up connection to named camera
            camera_index = zwoasi.list_cameras().index(camera_name)
            self.camera = zwoasi.Camera(camera_index)
            self.name = self.camera.get_camera_property()['Name']
        
        else:
            raise NameError('The camera you specified : {}, is not currently connected.'.format(camera_name))
    
        self.logger.info('Connection to {} created.'.format(self.name))

    
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
 
    def close_out(self):
        """ Closes camera and shuts down logging if you didn't use context managers.
        Note that this is named `close_out` and not close because the
        zwoasi.Camera object also has a close method and I'm trying not to
        overload it."""
        self._close_camera()
        self._close_logger()
    
    @zwo_except
    def list_connected_cameras(self):
        """ Lists currently connected cameras.
        
        Returns
        -------
        cameras : list of str
            List of camera names.
        """
        
        cameras = zwoasi.list_cameras()
        self.logger.info('Currently connected camers : {}'.format(cameras))

        return cameras

    @zwo_except
    def _open_camera(self, camera_name):
        """ Opens a connection to the camera. 
        
        Parameters
        ----------
        camera_name : str, optional
            The name of the camera to connect to. Defaults to whatever camera
            is first in line.
        """
        if camera_name=='default':
            # Open first camera connection 
            self.camera = zwoasi.Camera(0)
            self.name = self.camera.get_camera_property()['Name']
        
        elif camera_name in zwoasi.list_cameras():
            # Set up connection to named camera
            camera_index = zwoasi.list_cameras().index(camera_name)
            self.camera = zwoasi.Camera(camera_index)
            self.name = self.camera.get_camera_property()['Name']
        
        else:
            raise NameError('The camera you specified : {}, is not currently connected.'.format(camera_name))
    
        self.logger.info('Connection to {} created.'.format(self.name))

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
    
    def plot_image(self, image, colors='gray', norm='3-std', output_name='camera_test.png'):
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
            'camera_test.png'
        """

        # Set the appropriate scale normalization
        if 'std' in norm:
            factor = norm.split('-')[0]
            if factor.isdigit():
                factor = int(factor)
                v_min = np.median(image) - factor*np.std(image)
                v_max = np.median(image) + factor*np.std(image)
            else:
                raise ValueError("In order to use the 'x-std' normalization you need an int. Try '3-std'.")
        
        elif ',' in norm:
            try:
                v_min = float(norm.split(',')[0])
                v_max = float(norm.split(',')[1])
            except ValueError:
                raise ValueError("In order to use the 'x,y' normalization you need two numbers. Try '-2.1,400'")
        
        elif norm == 'min/max':
            v_min = np.min(image)
            v_max = np.max(image)

        elif norm == None:
            v_min, v_max = None, None

        else:
            raise NotImplementedError("The normalization scheme you tried doesn't exist.")

        # Save it
        plt.imshow(image, vmin=v_min, vmax=v_max, cmap=colors)
        plt.colorbar()
        plt.savefig(output_name)
        plt.clf()
        self.logger.info('Image saved to {}.'.format(output_name))
        
    def write_out_image(self, image, output_name='camera_test.fits'):
        """ Writes out the camera image to a FITS file.

        Parameters
        ----------
        image : np.array
            Np.array image output from `take_exposure`.
        output_name : str, optional
            Name of the output image. Includes path. Defaults to
            'camera_test.fits'.
        
        Notes
        -----
        If you don't specify a name and you're taking multiple images you will
        overwrite them each time.
        """
        
        # Write a header
        hdr = fits.Header()
        hdr['DATE'] = str(datetime.datetime.now())
        
        # Write out the file
        hdu = fits.PrimaryHDU(data=image, header=hdr)
        hdu.writeto(output_name, overwrite=True)

    def _close_camera(self):
        """Closes the camera."""
        try: 
            self.camera.close()
            self.logger.info('Camera connection closed.')
        except AttributeError:
            logger.info("There was no connected to camera to close.")
    
    def _close_logger(self):
        """ Closes the logging."""

        handlers = self.logger.handlers[:]
        for handler in handlers:
            handler.close()
            self.logger.removeHandler(handler)
    
# MAIN with ex
if __name__ == "__main__":
    with ZWOCamera() as zwo_cam:
        regular = zwo_cam.take_exposure()
        bright = zwo_cam.take_exposure(exp_time=10000)
        faint = zwo_cam.take_exposure(exp_time=100)
        
        zwo_cam.plot_image(regular, output_name='regular_image.png')
        zwo_cam.plot_image(bright, output_name='bright_image.png')
        zwo_cam.plot_image(faint, output_name='faint_image.png')
