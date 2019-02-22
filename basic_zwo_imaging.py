
import matplotlib.pyplot as plt
import pint
import zwoasi


def take_exposure(exp_time=1000, camera='ZWO', output_name='camera_test.png'):
    """ Stripping away the protections and pretty arcitecture of HiCAT with a
    simple function to take an exposure. Saves a plot of the image to whatever
    name specified.

    Parameters
    ----------
    exp_time : int, optinal
        Exposure time for the image in microseconds. Defaults to 1000.
    camera : str, optional
        Set to 'ZWO' by default. This will need to expand a touch come a
        complex system or multiple cameras.
    output_name : str, optional
        What to name the plot out; defaults to "camera_test.png".
    """

    # Set up units
    units = pint.UnitRegistry()
    quantity = units.Quantity

    # Intialize camera.
    # Right now this only works for a single connection to a ZWO camera.
    if camera = 'ZWO':
        cam_lib_file = 'C:/Users/RMOLStation1s/piezo_tiptilt/hicat-package/hicat/hardware/zwo/lib/windows/ASICamera2.dll'
        try:
            zwoasi.init(cam_lib_file)
        except Exception:
            raise ValueError("Something went wrong in the initialization. Maybe you gotta plug that camera in.")
    
        camera = zwoasi.list_cameras()[0]
    else:
        raise ValueError("There's no appropriate camera set up for you at this time.")
    
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

