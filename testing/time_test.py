import timeit 
  
mysetup = \
"""
import imageio
import glob
import numpy as np
"""

mycode1 = \
"""
from photutils import centroid_1dg
files = glob.glob('../images/*.png')
for image in files:
    im = imageio.imread(image)
    test_slice = np.array(im[:,:,0][145:350, 83:475])
    centroid_1dg(test_slice)
"""

mycode2 = \
"""
from photutils import centroid_2dg
files = glob.glob('../images/*.png')
for image in files:
    im = imageio.imread(image)
    test_slice = np.array(im[:,:,0][145:350, 83:475])
    centroid_2dg(test_slice)
"""

mycode3 = \
"""
from fake_centroid import fake_centroid
files = glob.glob('../images/*.png')
for image in files:
    im = imageio.imread(image)
    test_slice = np.array(im[:,:,0][145:350, 83:475])
    fake_centroid(test_slice)
"""

mycode4 = \
"""
from poppy import fwcentroid
files = glob.glob('../images/*.png')
for image in files:
    im = imageio.imread(image)
    test_slice = np.array(im[:,:,0][145:350, 83:475])
    fwcentroid.fwcentroid(test_slice)
"""

print("Test for 1d centroid.")
print(timeit.timeit(setup=mysetup, stmt=mycode1, number=50))
print("Test for 2d centroid.")
print(timeit.timeit(setup=mysetup, stmt=mycode2, number=50))
print("Test for fake centroid.")
print(timeit.timeit(setup=mysetup, stmt=mycode3, number=50))
print("Test for fwcentroid.")
print(timeit.timeit(setup=mysetup, stmt=mycode4, number=50))
