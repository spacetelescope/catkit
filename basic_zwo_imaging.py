## -- IMPORTS
import matplotlib.pyplot as plt
import pint
import zwoasi

## -- Quick convenience functions
def open_connection(camera_key='ZWO'):
    """ Function to initialize the camera and open a connection.
    Until we know the actual camera we're using this will pick the first
    'ZWO' camera it finds. 

    Parameters
    ----------
    camera_key : str, optional
        What camera to use. Right now defaults to 'ZWO' -- we don't have
        any other cameras set up at present. 
    """
    # Intialize camera.
    # Right now this only works for a single connection to a ZWO camera.
    if camera_key == 'ZWO':
        cam_lib_file = 'C:/Users/RMOLStation1s/piezo_tiptilt/hicat-package/hicat/hardware/zwo/lib/windows/ASICamera2.dll'
        try:
            zwoasi.init(cam_lib_file)
        except Exception:
            raise ValueError("Something went wrong in the initialization. Maybe you gotta plug that camera in.")
         
        camera = zwoasi.Camera(0)
    else:
        raise ValueError("There's no appropriate camera set up for you at this time.")

    return camera


def take_exposure(camera, exp_time=1000, output_name='camera_test.png'):
    """ Quick function to take a single exposure and write it to the given
    name. 

    Parameters
    ----------
    camera : zwoaslib.camera object 
        Camera object from the zwoaslib.
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
    image = camera.capture(
                inital_sleep=exposure_time.to(units.seconds).magnitude,
                poll=poll.magnitude)

    # Save it
    plt.imshow(image)
    plt.savefig(output_name)
    print('Image saved to {}.'.format(output_name))


def close_camera(camera):
    """Closes camera connection so we can live another day.

    camera : zwoasilib.camera object
        Camera object from the zwoasilib.
    """

    camera.close()


## -- RUN
if __name__ == "__main__":
    camera = open_connection()
    take_exposure(camera)
    close(camera)


