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
    if not resn.detector:
        return None
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

    tdecay_s = float(resn.tdecay)

    row: dict = {
        "_tdecay_s": tdecay_s,
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


def _build_summary_sheet(
    writer: pd.ExcelWriter,
    summary_rows: list[dict],
    volume: float,
) -> None:
    if not summary_rows:
        return
    sorted_rows = sorted(
        summary_rows,
        key=lambda r: (r["_tdecay_s"], str(r.get("CoolingTime", ""))),
    )
    bq_cols = [c for c in summary_rows[0] if c.endswith("(Bq)")]
    meta_cols = [c for c in summary_rows[0] if not c.startswith("_") and not c.endswith("(Bq)")]

    df_raw = pd.DataFrame(sorted_rows)[meta_cols + bq_cols]

    df_norm = df_raw[meta_cols].copy()
    for col in bq_cols:
        df_norm[col.replace("(Bq)", "(Bq/cm³)")] = df_raw[col] / volume

    sheet_name = "Summary"
    n = len(df_raw)
    df_raw.to_excel(writer, sheet_name=sheet_name, startrow=1, index=False)
    df_norm.to_excel(writer, sheet_name=sheet_name, startrow=n + 4, index=False)

    ws = writer.sheets[sheet_name]
    ws.cell(row=1, column=1, value="Activity (Bq)")
    ws.cell(row=n + 4, column=1, value=f"Normalized Activity (Bq/cm³) — volume: {volume} cm³")


def _build_pivot_sheet(
    writer: pd.ExcelWriter,
    summary_rows: list[dict],
    param_names: list[str],
    group_by: Optional[str],
    volume: float,
) -> None:
    if not summary_rows:
        return

    sheet_name = "Pivot"

    if group_by is not None:
        seen: list[str] = []
        buckets: dict[str, list[dict]] = {}
        for r in summary_rows:
            v = str(r[group_by])
            if v not in buckets:
                seen.append(v)
                buckets[v] = []
            buckets[v].append(r)
        group_items = [(v, buckets[v]) for v in seen]
        column_params = [p for p in param_names if p != group_by]
    else:
        group_items = [(None, summary_rows)]
        column_params = param_names[:]

    if not column_params:
        return

    excel_row = 1  # 1-indexed; startrow=N writes to Excel row N+1

    for group_value, rows in group_items:
        df = pd.DataFrame(rows)
        bq_cols = [c for c in df.columns if c.endswith("(Bq)")]

        ct_order = (
            df[["_tdecay_s", "CoolingTime"]]
            .drop_duplicates()
            .sort_values("_tdecay_s")["CoolingTime"]
            .tolist()
        )
        df["CoolingTime"] = pd.Categorical(
            df["CoolingTime"], categories=ct_order, ordered=True
        )

        df_melt = df.melt(
            id_vars=["CoolingTime"] + column_params,
            value_vars=bq_cols,
            var_name="Isotope",
            value_name="Bq",
        )
        df_melt["Isotope"] = df_melt["Isotope"].str.replace(r" \(Bq\)$", "", regex=True)

        pivot_bq = df_melt.pivot_table(
            index=["Isotope", "CoolingTime"],
            columns=column_params,
            values="Bq",
            aggfunc="first",
            observed=True,
        )

        n_col_levels = pivot_bq.columns.nlevels
        n_data = len(pivot_bq)

        bq_title = f"{group_by}={group_value}" if group_value is not None else "Activity (Bq)"
        pivot_bq.to_excel(writer, sheet_name=sheet_name, startrow=excel_row)
        ws = writer.sheets[sheet_name]
        ws.cell(row=excel_row, column=1, value=bq_title)
        excel_row += 1 + n_col_levels + n_data

        excel_row += 1  # 1-row gap

        pivot_norm = pivot_bq / volume
        norm_title = f"Normalized Activity (Bq/cm³) — volume: {volume} cm³"
        pivot_norm.to_excel(writer, sheet_name=sheet_name, startrow=excel_row)
        ws.cell(row=excel_row, column=1, value=norm_title)
        excel_row += 1 + n_col_levels + n_data

        excel_row += 2  # 2-row gap before next group


def run_isotope_analysis(
    output_dir: Path,
    config,
    state,
    combo: Optional[str] = None,
) -> None:
    ia = config.isotope_analysis
    combos = [combo] if combo else list(state.data.keys())
    sheets: dict[str, pd.DataFrame] = {}
    isotope_syms = [isotope_symbol(z, a) for z, a in sorted(ia.isotopes.items())]
    summary_rows: list[dict] = []

    for combo_name in combos:
        combo_data = state.data.get(combo_name)
        if combo_data is None:
            continue
        params = combo_data.get("parameters", {})
        postproc_dir = output_dir / combo_name / "postproc"
        rows = []
        for rnc_file in ia.rnc_files:
            row = read_resnuclei_file(postproc_dir / rnc_file, ia.isotopes, params)
            if row is not None:
                rows.append(row)
                summary_row: dict = {
                    "_tdecay_s": row["_tdecay_s"],
                    "CoolingTime": row["CoolingTime"],
                    **params,
                }
                for sym in isotope_syms:
                    summary_row[f"{sym} (Bq)"] = row.get(f"{sym} (Bq)", 0.0)
                summary_rows.append(summary_row)
        if rows:
            sheets[combo_name[:31]] = pd.DataFrame(rows).drop(columns=["_tdecay_s"], errors="ignore")
        else:
            print(f"[analyze] {combo_name}: no data found, skipping")

    if not sheets:
        print("[analyze] No data found for any combo")
        return

    output_path = output_dir / ia.output
    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        _build_summary_sheet(writer, summary_rows, ia.volume)
    print(f"[analyze] Written {output_path}")
