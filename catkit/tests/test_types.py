import numpy as np

from catkit.catkit_types import units, quantity


def test_quantity():
    a = quantity(10, units.microseconds)
    assert isinstance(a, units.Quantity)
    assert isinstance(a, quantity)
    assert a.magnitude == 10

    # Check against creation of compound quantities.
    b = quantity(a, units.microseconds)
    assert isinstance(b.magnitude, int)

    # Check unit conversion when attempting compound quantity creation.
    c = quantity(b, units.seconds)
    assert isinstance(c.magnitude, float)
    assert np.isclose(c.magnitude, 10e-6)

    d = quantity(2)
    assert d.magnitude == 2

    # Test that compounding hasn't been addressed upstream.
    e = units.Quantity(units.Quantity(5, units.seconds), units.seconds)
    assert isinstance(e.magnitude, units.Quantity)
    assert e.magnitude.magnitude == 5

    f = units.Quantity(units.Quantity(5, units.seconds), units.microseconds)
    assert isinstance(f.magnitude, units.Quantity)
    assert f.magnitude.magnitude == 5

    g = quantity(quantity(9, "seconds"), "microseconds")
    assert isinstance(a, units.Quantity)
    assert np.isclose(g.magnitude, 9e6)
