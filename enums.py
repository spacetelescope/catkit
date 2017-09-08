from __future__ import (absolute_import, division,
                        print_function, unicode_literals)
# noinspection PyUnresolvedReferences
from builtins import *
from enum import Enum


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