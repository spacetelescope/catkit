import configparser
import os

from catkit.catkit_types import Pointer
from catkit.util import find_package_location

config_file_name = "config.ini"
override_file_name = "config_local.ini"

"""
The intended use pattern is to not directly parse and import the config.ini each time
but to instead, parse it once and then import it via `from package.config import CONFIG_INI`.
"""
# All global state of the parsed config will be assigned to CONFIG_INI.
# Initial pointer that will be "loaded" from downstream package by calling to `load_config_ini()`.
CONFIG_INI = Pointer(None)


config_file_name = "config.ini"
override_file_name = "config_local.ini"


def get_config_ini_path(package):
    package_dir = find_package_location(package)
    config_path = os.path.join(package_dir, config_file_name)

    # Check if there is a local override config file (which is ignored by git).
    local_override_path = os.path.join(package_dir, override_file_name)
    if os.path.exists(local_override_path):
        config_path = local_override_path

    return config_path


def load_config_ini(config_filename):
    global CONFIG_INI

    # Read config file once here.
    config = configparser.ConfigParser()
    config._interpolation = configparser.ExtendedInterpolation()
    config.read(config_filename)

    CONFIG_INI.point_to(config)
    return config
