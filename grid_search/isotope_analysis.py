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


def read_resnuclei_file(
    path: Path,
    requested_isotopes: dict[int, int],
    params: dict,
) -> Optional[dict]:
    if not path.exists():
        return None

    resn = Resnuclei(str(path))
    det = resn.detector[0]
    data = resn.read_data(0)
    stat = resn.read_stat(0)
    fdata = unpack_array(data)
    edata = unpack_array(stat[5]) if stat is not None else None

    zhigh = det.zhigh
    mhigh = det.mhigh
    nmzmin = det.nmzmin
    volume = det.volume
    amax = 2 * zhigh + mhigh + nmzmin

    lookup: dict[tuple[int, int], tuple[float, float]] = {}
    for a in range(1, amax + 1):
        for z in range(zhigh):
            z_actual = z + 1
            m = a - 2 * z - nmzmin - 3
            if m < 0 or m >= mhigh:
                lookup[(z_actual, a)] = (0.0, 0.0)
            else:
                pos = z + m * zhigh
                bq = fdata[pos] * volume
                bq_err = (edata[pos] * fdata[pos] * volume) if edata is not None else 0.0
                lookup[(z_actual, a)] = (bq, bq_err)

    tdecay = resn.tdecay
    tdecay_s = tdecay[0] if isinstance(tdecay, tuple) else float(tdecay)

    row: dict = {
        "CoolingTime": format_decay_time(tdecay_s),
        "Parameters": " ".join(f"{k}={v}" for k, v in params.items()),
    }
    for z, a in sorted(requested_isotopes.items()):
        sym = isotope_symbol(z, a)
        bq, bq_err = lookup.get((z, a), (0.0, 0.0))
        pct_err = (bq_err / bq * 100) if bq != 0 else 0.0
        hl = half_life(z, a)
        mm = molar_mass(z, a)
        ug = (bq * mm * hl) / (_AVOGADRO * math.log(2)) * 1e6 if (hl > 0 and mm > 0) else 0.0
        row[f"{sym} (Bq)"] = bq
        row[f"{sym} (% Error)"] = pct_err
        row[f"{sym} (µg)"] = ug
    return row


def run_isotope_analysis(
    output_dir: Path,
    config,
    state,
    combo: Optional[str] = None,
) -> None:
    ia = config.isotope_analysis
    combos = [combo] if combo else list(state.data.keys())
    sheets: dict[str, pd.DataFrame] = {}

    for combo_name in combos:
        combo_data = state.data.get(combo_name)
        if not combo_data:
            continue
        params = combo_data.get("parameters", {})
        postproc_dir = output_dir / combo_name / "postproc"
        rows = []
        for rnc_file in ia.rnc_files:
            row = read_resnuclei_file(postproc_dir / rnc_file, ia.isotopes, params)
            if row is not None:
                rows.append(row)
        if rows:
            sheets[combo_name[:31]] = pd.DataFrame(rows)
        else:
            print(f"[analyze] {combo_name}: no data found, skipping")

    if not sheets:
        print("[analyze] No data found for any combo")
        return

    output_path = output_dir / ia.output
    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    print(f"[analyze] Written {output_path}")
