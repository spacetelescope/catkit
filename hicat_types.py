from __future__ import (absolute_import, division,
                        print_function, unicode_literals)
# noinspection PyUnresolvedReferences
from builtins import *
from enum import Enum


class HicatImagingProducts:
    """Simple container to hold the output parameters of the run_hicat_imaging function. Generic constructor
    implemented, although only use keyword arguments for the class variables listed. First use isn't passing
    any keyword params, and is instead populating the container one by one."""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    img_data = None
    bg_data = None
    img_paths = None
    bg_paths = None
    cal_data = None
    cal_path = None
    img_metadata = None
    bg_metadata = None


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
