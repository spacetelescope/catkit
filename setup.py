import os
from setuptools import setup

setup(name='interfaces',
      version='0.1',
      description='Pure Python hardware interfaces for the Optics Lab.',
      url='https://github.com/spacetelescope/instrument-interface-library',
      author='Jules Fowler',
      license='MIT',
      packages=['interfaces'],
      zip_safe=False)

directories = ['logs', 'images']
for directory in directories:
    if os.path.exists(directory) == False:
        os.makedirs(directory)
    else:
        print('The {} directory is already in place.'.format(directory))

import interfaces
cmd = 'export INTERFACES="{}"'.format(interfaces.__path__[0].replace('interfaces', ''))
print("Add this line to your .bashrc :")
print(cmd)
