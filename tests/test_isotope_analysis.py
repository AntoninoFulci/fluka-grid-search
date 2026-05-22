import pytest
from grid_search.isotope_analysis import (
    isotope_symbol,
    molar_mass,
    half_life,
    format_decay_time,
)


def test_isotope_symbol_co60():
    assert isotope_symbol(27, 60) == "Co-60"


def test_isotope_symbol_cs137():
    assert isotope_symbol(55, 137) == "Cs-137"


def test_molar_mass_co60_positive():
    mass = molar_mass(27, 60)
    assert isinstance(mass, float)
    assert mass > 50.0


def test_molar_mass_unknown_returns_zero():
    assert molar_mass(999, 999) == 0.0


def test_half_life_co60_positive():
    hl = half_life(27, 60)
    assert isinstance(hl, float)
    assert hl > 0.0


def test_half_life_unknown_returns_zero():
    assert half_life(999, 999) == 0.0


def test_format_decay_time_seconds():
    assert format_decay_time(30) == "30 s"


def test_format_decay_time_minutes():
    assert format_decay_time(120) == "2 min"


def test_format_decay_time_hours():
    assert format_decay_time(7200) == "2 h"


def test_format_decay_time_days():
    result = format_decay_time(3 * 86400)
    assert "d" in result


def test_format_decay_time_zero():
    assert format_decay_time(0) == "0 s"
