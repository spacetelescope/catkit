
import matplotlib.pyplot as plt
import pint
import zwoasi

# Unit set up?
units = pint.UnitRegistry()
quantity = units.Qauntity

# Pick out the right camera
camera_name = 'ZWhatever...'
cameras_found = zwoasi.list_cameras()
camera_index = cameras_found.index(camera_name)

camera = zwoasi.Camera(camera_index)

# Set the image specifics (bare minimum)
poll = quantity(0.1, units.second)
exposure_time = quantity(1000, units.microsecond)

# Take the image
image = camera.capture(initial_sleep=exposure_time.to(units.second).magnitude, poll=poll.magnitude)
plt.imshow(image)
plt.savefig('test_img.png')

"""
AttributeError: 'NoneType' object has no attribute 'ASIGetNumOfCOnnectedCameras'
"""



