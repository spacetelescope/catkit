## -- IMPORTS
try:
    from astropy.io import fits
    import matplotlib.pyplot as plt
    import numpy as np
    from photutils import centroid_2dg
except ImportError:
    print('This requires : astropy, matplotlib, numpy, and photutils.')
    print('Please install them with pip/conda and try again...')
## -- RUN

# Open file
image_file = '/users/jfowler/Desktop/target_ac_im_2019-2-21.fits' # replace this with where you put the file on your machine
with fits.open(image_file) as hdu:
    image_data = hdu[0].data
    hdr = hdu[0].header

# Now we have some image data in the form of a numpy array and some header keys.
print('Demo slice of the image:')
print(image_data[300:303, 400:404])
print('Header keys:')
for key in hdr:
    print('{} : {}'.format(key, hdr[key]))

# Now find the centroid of the data
x, y = centroid_2dg(image_data)
print('Centroid of the image is : ({},{}).'.format(x,y))

# Now plot the image, with the centroid marked.
v_min = np.median(image_data) - 3*np.std(image_data)
v_max = np.median(image_data) + 3*np.std(image_data)
plt.imshow(image_data, cmap='gray', vmin=v_min, vmax=v_max)
plt.plot(x, y, 'o', color='green')
plt.savefig('test_centroid.png')
print("Centroid + image plot saved to 'test_centroid.png'")
