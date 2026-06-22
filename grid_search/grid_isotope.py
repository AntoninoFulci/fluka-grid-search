from __future__ import annotations
from pathlib import Path
from typing import Optional

import pandas as pd

from isotope_analysis.reader import read_resnuclei_file
from isotope_analysis.physics import isotope_symbol


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

    group_items: list[tuple[Optional[str], list[dict]]]
    if group_by is not None:
        buckets: dict[str, list[dict]] = {}
        for r in summary_rows:
            buckets.setdefault(str(r[group_by]), []).append(r)
        group_items = list(buckets.items())
        column_params = [p for p in param_names if p != group_by]
    else:
        group_items = [(None, summary_rows)]
        column_params = param_names[:]

    if not column_params:
        return

    # excel_row is 1-indexed (matches openpyxl ws.cell row arg).
    # pd.to_excel startrow is 0-indexed, so startrow=excel_row writes
    # the first header/data row at Excel row excel_row+1.
    excel_row = 1

    for group_value, rows in group_items:
        df = pd.DataFrame(rows)
        bq_cols = [c for c in df.columns if c.endswith("(Bq)")]
        if not bq_cols:
            continue

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
        _build_pivot_sheet(
            writer,
            summary_rows,
            list(config.grid.parameters.keys()),
            ia.pivot_group_by,
            ia.volume,
        )
    print(f"[analyze] Written {output_path}")
