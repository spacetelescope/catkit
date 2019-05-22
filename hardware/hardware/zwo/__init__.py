from __future__ import (absolute_import, division,
                        unicode_literals)
# noinspection PyUnresolvedReferences

import os
import platform

# Set up environment variable needed by zwoasi library.

env_filename = os.getenv('ZWO_ASI_LIB')
if not env_filename:
    code_directory = os.path.dirname(os.path.realpath(__file__)) + "/"
    if platform.system().lower() == "darwin":
        os.environ["ZWO_ASI_LIB"] = code_directory + \
            "/lib/mac/libASICamera2.dylib"
    elif platform.system().lower() == "windows":
        os.environ["ZWO_ASI_LIB"] = code_directory + \
            "/lib/windows/ASICamera2.dll"
    else:
        os.environ["ZWO_ASI_LIB"] = code_directory + \
            "/lib/linux/libASICamera2.so"
