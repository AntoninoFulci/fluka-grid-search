from __future__ import annotations
import math
from pathlib import Path
from typing import Optional

import periodictable
import radioactivedecay as rd
import pandas as pd

from .resnuclei import Resnuclei, unpack_array

_AVOGADRO = 6.02214076e23


def isotope_symbol(z: int, a: int) -> str:
    element = periodictable.elements[z]
    return f"{element.symbol}-{a}"


def molar_mass(z: int, a: int) -> float:
    try:
        nuc = rd.Nuclide(isotope_symbol(z, a))
        return float(nuc.atomic_mass)
    except (ValueError, KeyError):
        return 0.0


def half_life(z: int, a: int) -> float:
    try:
        nuc = rd.Nuclide(isotope_symbol(z, a))
        hl = nuc.half_life()
        if hl is None or hl == "stable" or (isinstance(hl, float) and math.isinf(hl)):
            return 0.0
        return float(hl)
    except (ValueError, KeyError):
        return 0.0


def format_decay_time(seconds: float) -> str:
    if seconds <= 0:
        return "0 s"
    minute = 60.0
    hour = 3600.0
    day = 86400.0
    week = 7 * day
    month = 30 * day
    year = 365.25 * day
    if seconds < minute:
        return f"{round(seconds)} s"
    elif seconds < hour:
        return f"{int(seconds / minute)} min"
    elif seconds < day:
        return f"{int(seconds / hour)} h"
    elif seconds < week:
        return f"{seconds / day:.1f} d"
    elif seconds < month:
        return f"{seconds / week:.1f} weeks"
    elif seconds < year:
        return f"{seconds / month:.1f} months"
    else:
        return f"{seconds / year:.1f} y"
