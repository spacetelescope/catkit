from __future__ import (absolute_import, division,
                        unicode_literals)
# noinspection PyUnresolvedReferences
from builtins import *
import os

try:
    import zwoasi

    # Importing zwoasi doesn't hook it up to the backend driver, we have to unfortunately do this.
    # This is achieved by zwoasi.init(<file to ASI SDK lib>)

    # NOTE: The ZWO ASI SDK can be downloaded from https://astronomy-imaging-camera.com/software-drivers
    # Windows requires additional drivers also from https://astronomy-imaging-camera.com/software-drivers

    __ZWO_ASI_LIB = 'ZWO_ASI_LIB'
    __env_filename = os.getenv(__ZWO_ASI_LIB)

    if not __env_filename:
        raise OSError(
            "Environment variable '{}' doesn't exist. Create and point to ASICamera2 lib".format(__ZWO_ASI_LIB))
    if not os.path.exists(__env_filename):
        raise OSError("File not found: '{}' -> '{}'".format(__ZWO_ASI_LIB, __env_filename))

    try:
        zwoasi.init(__env_filename)
    except zwoasi.ZWO_Error as error:
        if str(error) == 'Library already initialized':  # weak but better than nothing...
            # Library already initialized, continuing...
            pass
        else:
            raise
except Exception as error:
    raise ImportError("Failed to import zwoasi") from error
