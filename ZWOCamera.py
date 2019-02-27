
import matplotlib.pyplot as plt
import pint
import zwoasi

## -- CLASS DEF

class ZWOCamera:
    """Class for the ZWOCamera. """
    
    def __init__(self):
        """ Init funciton to set up logging and instantiate the camera."""

        # 3 logging 5 me
        cam_lib_file = 'C:/Users/RMOLStation1s/piezo_tiptilt/hicat-package/hicat/hardware/zwo/lib/windows/ASICamera2.dll'
        try:
            zwoasi.init(cam_lib_file)
            self.camera = zwoasi.Camera(0)
        except (zwoasi.ZWO_Error, zwoasi.ZWO_IOError, zwoasi.ZWO_CaptureError) as e:
            

    def __enter__(self):
        """ Enter function to allow for context management."""
        return

    def __exit__(self):
        """ Exit function to allow for context management. In this case, closes
        the camera."""
        self.camera.close()

    def take_exposure(exp_time=1000, output_name='camera_test.png'):
        """ Quick function to take a single exposure and write it to the given
        name. 

        Parameters
        ----------
        exp_time : int, optinal
            Exposure time for the image in microseconds. Defaults to 1000.
        output_name : str, optional
            What to name the plot out; defaults to "camera_test.png".
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
                    inital_sleep=exposure_time.to(units.seconds).magnitude,
                    poll=poll.magnitude)
 
        # Save it
        plt.imshow(image)
        plt.savefig(output_name)
        print('Image saved to {}.'.format(output_name))

    def close_camera(self):
        """Closes the camera if you didn't use context managers."""
        self.camera.close()

