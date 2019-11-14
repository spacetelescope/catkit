from collections import namedtuple
from enum import Enum
from pint import UnitRegistry


class BeamDumpPosition(Enum):
    """
    Enum for the possible states of the Beam Dump.
    """
    in_beam = 1
    out_of_beam = 2


class FpmPosition(Enum):
    """
    Enum for the possible states for the focal plane mask.
    """
    coron = 1
    direct = 2


class LyotStopPosition(Enum):
    """
    Enum for the possible states for the lyot stop.
    """
    in_beam = 1
    out_of_beam = 2


class ImageCentering(Enum):
    """
    Enum for the image centering options.
    """
    off = 1
    auto = 2
    psf = 3
    satellite_spots = 4
    injected_speckles = 5
    custom_apodizer_spots = 6
    cross_correlation = 7
    global_cross_correlation = 8
    xy_sym = 9


# Create a named tuple to hold metadata
MetaDataEntry = namedtuple("MetaDataEntry", "name, name_8chars, value, comment")


# Named Tuple as a container for sine wave specifications. peak_to_valley must be a pint quantity.
SinSpecification = namedtuple("SinSpecification", "angle, ncycles, peak_to_valley, phase")


# Create shortcuts for using Pint globally.
units = UnitRegistry()
quantity = units.Quantity
