# Isotope Pivot Sheet Design

**Date:** 2026-05-22
**Status:** Approved

## Overview

Add a "Pivot" sheet to the existing `isotopes.xlsx` output. The sheet reorganises the isotope activity data from the per-combo/Summary linear layout into a cross-tab pivot: grid parameters form nested column headers, isotopes × cooling times form the row index.

## Goal

Given a grid search over N parameters (e.g. `mat`, `beame`, `rzmin`, `tzmax`), produce a compact table where a physicist can read off the activity of every isotope at every cooling time for every parameter combination without scrolling through separate sheets.

## Layout

One optional parameter (`pivot_group_by`) designates a "table-level" grouper. For each unique value of that parameter the sheet contains one Bq block immediately followed by one Bq/cm³ block, then a 2-row gap before the next group.

```
[Title: mat=GALLIUM]
[Column header row 1: beame    | 0.5  0.5 ... | 0.1  ... ]
[Column header row 2: rzmin    | -8  -7.6 ... | -8   ... ]
[Column header row 3: tzmax    |  5  -4   ... |  5   ... ]
[Data — Bq:
  Ga-70  | 0 s  | ...
         | 1 d  | ...
         | 7 d  | ...
  Zn-69  | 0 s  | ...
         | ...  | ...
]
[1-row gap]
[Title: Normalized Activity (Bq/cm³) — volume: X cm³]
[Same column headers]
[Same rows, values / volume]
[2-row gap]
[Title: mat=TUNGSTEN]
...
```

If `pivot_group_by` is absent the entire dataset is treated as one group (no grouper title row, single Bq + Bq/cm³ block).

### Column MultiIndex

- Levels = remaining grid parameters after removing `pivot_group_by`, in config order
- Labels = raw parameter names from `config.yaml` (e.g. `beame`, `rzmin`)
- openpyxl merges cells automatically via `df.to_excel(merge_cells=True)` (default)

### Row MultiIndex

- Level 0: isotope symbol (e.g. `Ga-70`, `Zn-69`), sorted by Z
- Level 1: `CoolingTime` string (e.g. `0 s`, `1 d`, `7 d`), ordered by ascending `_tdecay_s`
- Implemented as `pd.Categorical` so `pivot_table` respects physical order, not alphabetical

## Config Changes

`IsotopeConfig` gains one new optional field:

```yaml
isotope_analysis:
  pivot_group_by: mat   # optional; omit to produce a single un-grouped pivot
```

Accepted values: any parameter name present in `grid.parameters`. If not set, defaults to `None`.

## Implementation

### Files changed

| File | Change |
|---|---|
| `grid_search/config.py` | Add `pivot_group_by: Optional[str] = None` to `IsotopeConfig`; read from yaml in `load_config` |
| `grid_search/isotope_analysis.py` | Add `_build_pivot_sheet`; call it from `run_isotope_analysis` |

### `_build_pivot_sheet` algorithm

```
def _build_pivot_sheet(writer, summary_rows, param_names, group_by, volume):
    groups = group summary_rows by group_by value, preserving config order
               (or [(None, summary_rows)] if group_by is None)

    current_row = 0

    for group_value, rows in groups:
        df = DataFrame(rows)
        bq_cols = columns ending with "(Bq)"
        column_params = param_names minus group_by

        cooling_order = unique CoolingTime values sorted by _tdecay_s
        df["CoolingTime"] = Categorical(df["CoolingTime"], categories=cooling_order, ordered=True)

        df_melt = df.melt(
            id_vars=["CoolingTime"] + column_params,
            value_vars=bq_cols,
            var_name="Isotope", value_name="Bq"
        )
        df_melt["Isotope"] = strip " (Bq)" suffix

        pivot_bq = df_melt.pivot_table(
            index=["Isotope", "CoolingTime"],
            columns=column_params,
            values="Bq",
            aggfunc="first"
        )
        # row order: isotopes sorted by Z (derived from symbol), cooling times by Categorical

        # write Bq block
        if group_value is not None:
            ws.cell(current_row+1, 1, f"mat={group_value}")   # title
            current_row += 1
        pivot_bq.to_excel(writer, sheet_name="Pivot", startrow=current_row)
        current_row += len(column_params) + len(pivot_bq) + 1  # headers + data + gap

        # write Bq/cm³ block
        pivot_norm = pivot_bq / volume
        ws.cell(current_row+1, 1, f"Normalized Activity (Bq/cm³) — volume: {volume} cm³")
        current_row += 1
        pivot_norm.to_excel(writer, sheet_name="Pivot", startrow=current_row)
        current_row += len(column_params) + len(pivot_norm) + 3  # headers + data + gap
```

### Isotope row ordering

Isotope symbols (`Ga-70`, `Zn-69`) are sorted by atomic number Z. Z is already available from `ia.isotopes` (dict `{Z: A}`), so `isotope_syms` (already built in `run_isotope_analysis`) can be used directly as the canonical order.

### Integration in `run_isotope_analysis`

```python
with pd.ExcelWriter(...) as writer:
    for sheet_name, df in sheets.items():
        df.to_excel(...)
    _build_summary_sheet(writer, summary_rows, ia.volume)
    _build_pivot_sheet(
        writer,
        summary_rows,
        list(config.grid.parameters.keys()),
        ia.pivot_group_by,
        ia.volume,
    )
```

## Testing

Extend `tests/test_postprocess.py` (or add a new file `tests/test_pivot_sheet.py`) with:

- **Unit test for `_build_pivot_sheet`**: synthetic `summary_rows` with 2 materials × 2 beam energies × 2 isotopes × 2 cooling times → assert sheet "Pivot" exists, correct number of rows, correct MultiIndex column levels, correct values, correct Bq/cm³ values
- **Group-by absent**: assert single block produced (no group title row)
- **Cooling time order**: assert that a later-in-seconds cooling time always appears below an earlier one regardless of string sort order

## No new dependencies

Uses pandas + openpyxl already present.
