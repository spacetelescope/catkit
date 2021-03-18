from collections import namedtuple
from enum import Enum

import astropy.units


class ColorWheelFilter(Enum):
    def __init__(self, filter_name, wavelength, position):
        self.filter_name = filter_name
        self.wavelength = wavelength
        self.position = position

    @classmethod
    def _missing_(cls, value):
        for item in cls:
            if value in (item.filter_name, f"filter_{item.filter_name}", item.wavelength, str(item.wavelength), item.position):
                return item


class NDWheelFilter(Enum):
    def __init__(self, filter_name, transmittance, position):
        self.filter_name = filter_name
        self.transmittance = transmittance
        self.position = position

    @classmethod
    def _missing_(cls, value):
        for item in cls:
            if value in (item.filter_name, f"filter_{item.filter_name}", item.transmittance, item.position):
                return item


class FlipMountPosition(Enum):
    """
    Enum for the possible states of the Beam Dump.
    """
    IN_BEAM = "in_beam_position"
    OUT_OF_BEAM = "out_of_beam_position"


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
    IN_BEAM = 1
    OUT_OF_BEAM = 2


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


class Quantity(astropy.units.Quantity):
    """ HICAT-466: Path of least resistance to using astropy.units instead of pint.
        This class wraps astropy.units.Quantity as a pint.Quantity (for only hicat's function usage cross-section).
    """
    @property
    def magnitude(self):
        return self.value

    @property
    def m(self):
        return self.magnitude

    @property
    def u(self):
        return self.unit

    def to_base_units(self):
        return self.si

    def __round__(self, n=None):
        return self.round(decimals=n)

    # See https://docs.astropy.org/en/stable/units/quantity.html#subclassing-quantity
    def __quantity_subclass__(self, unit):
        """
        Overridden by subclasses to change what kind of view is
        created based on the output unit of an operation.

        Parameters
        ----------
        unit : UnitBase
            The unit for which the appropriate class should be returned

        Returns
        -------
        tuple :
            - `Quantity` subclass
            - bool: True if subclasses of the given class are ok
        """
        return Quantity, True


units = astropy.units
quantity = Quantity


class Pointer:
    def __init__(self, ref):
        super().__getattribute__("point_to")(ref)

    def __getattribute__(self, name):
        if name == "self":
            return super().__getattribute__("ref")
        elif name == "point_to":
            return super().__getattribute__(name)
        else:
            return super().__getattribute__("ref").__getattribute__(name)

    def __setattr__(self, name, value):
        super().__getattribute__("ref").__setattr__(name, value)

    def __delattr__(self, name):
        super().__getattribute__("ref").__delattr__(name)

    def __dir__(self, name):
        super().__getattribute__("ref").__dir__(name)

    def point_to(self, ref):
        super().__setattr__("ref", ref)
