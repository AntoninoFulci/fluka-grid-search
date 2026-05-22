# Isotope Analysis — Summary Sheet Design Spec

## Goal

Add a `"Summary"` sheet to the Excel output of `--analyze` that consolidates all grid-search combos and cooling times into two stacked flat tables: one for absolute activity (Bq) and one normalized by a reference volume (Bq/cm³). This lets the user identify the best parameter setup at a glance without switching between per-combo sheets.

## Config Change

`IsotopeConfig` gains one optional field:

```yaml
isotope_analysis:
  volume: 10.0    # cm³ — reference volume for normalization. Defaults to 1.0.
  isotopes:
    31: 70
    30: 69
  rnc_files:
    - merged_21.rnc
```

`volume` defaults to `1.0` when absent, making Bq/cm³ = Bq (safe no-op).

## Summary Sheet Structure

Sheet name: `"Summary"` — always written last in the Excel file.

```
Activity (Bq)
CoolingTime | beame | mat     | Zn-69 (Bq) | Ga-70 (Bq)
0 s         | 0.05  | GALLIUM | 1.33e12    | 1.12e15
0 s         | 0.10  | GALLIUM | 9.18e12    | 2.80e15
0 s         | 0.50  | GALLIUM | 4.81e13    | 1.06e16
1.0 d       | 0.05  | GALLIUM | 3.92e10    | 3.49e-06
...

[blank row]

Normalized Activity (Bq/cm³) — volume: 10.0 cm³
CoolingTime | beame | mat     | Zn-69 (Bq/cm³) | Ga-70 (Bq/cm³)
0 s         | 0.05  | GALLIUM | 1.33e11         | 1.12e14
...
```

### Row ordering
Rows sorted by `tdecay` (seconds, ascending) first, then by combo name. This groups all parameter combos together at each cooling time, making it easy to compare setups at a given decay time.

### Columns
- `CoolingTime` — human-readable string (e.g. `"1.0 d"`)
- One column per grid parameter (`beame`, `mat`, …) — sourced directly from `state.data[combo]["parameters"]`, not parsed from the `Parameters` string
- One `{Symbol} (Bq)` column per requested isotope (Table 1)
- One `{Symbol} (Bq/cm³)` column per requested isotope (Table 2), computed as `Bq / volume`

Only Bq values appear in the summary. `% Error` and `µg` remain in the per-combo sheets.

## Data Flow

```
run_isotope_analysis
    │
    ├── for each combo × rnc_file:
    │       row = read_resnuclei_file(...)   ← now includes "_tdecay_s" (float seconds, internal)
    │       rows.append(row)                 ← for per-combo sheet
    │       summary_rows.append(             ← for summary
    │           {CoolingTime, _tdecay_s,
    │            **params_dict,              ← expanded: {beame: 0.05, mat: "GALLIUM"}
    │            Symbol (Bq): ...}
    │       )
    │
    ├── write per-combo sheets               ← drop "_tdecay_s" before writing
    │
    └── _build_summary_sheet(writer, summary_rows, volume)
            ├── sort by (_tdecay_s, combo_name)
            ├── build raw-Bq DataFrame       ← drop "_tdecay_s"
            ├── build normalized DataFrame   ← Bq / volume, rename columns to Bq/cm³
            └── write both to "Summary" sheet with title rows via openpyxl API
```

## Implementation Details

### Modified files

**`grid_search/config.py`**
- Add `volume: float = 1.0` to `IsotopeConfig`
- Parse `ia_raw.get("volume", 1.0)` in `load_config`

**`grid_search/isotope_analysis.py`**

`read_resnuclei_file` — add one line after computing `tdecay_s`:
```python
row["_tdecay_s"] = tdecay_s   # internal sort key, stripped before writing to Excel
```

`run_isotope_analysis` — three changes:
1. Drop `_tdecay_s` from per-combo DataFrames before writing:
   ```python
   df = pd.DataFrame(rows).drop(columns=["_tdecay_s"], errors="ignore")
   ```
2. Accumulate `summary_rows` inside the combo loop:
   ```python
   isotope_syms = [isotope_symbol(z, a) for z, a in sorted(ia.isotopes.items())]
   # ...inside combo loop, after rows.append(row):
   summary_row = {"CoolingTime": row["CoolingTime"], "_tdecay_s": row["_tdecay_s"], **params}
   for sym in isotope_syms:
       summary_row[f"{sym} (Bq)"] = row.get(f"{sym} (Bq)", 0.0)
   summary_rows.append(summary_row)
   ```
3. After writing combo sheets, call `_build_summary_sheet(writer, summary_rows, ia.volume)`.

`_build_summary_sheet(writer, summary_rows, volume)` — new private function:
- Sort rows by `("_tdecay_s", combo sort key)`
- Identify `meta_cols` = non-`_`, non-`(Bq)` columns: `CoolingTime`, param columns
- Identify `bq_cols` = columns ending in `(Bq)`
- Build `df_raw = DataFrame[meta_cols + bq_cols]`
- Build `df_norm = df_raw[meta_cols]` + Bq/volume columns renamed to `(Bq/cm³)`
- Write `df_raw` at `startrow=1`, title at row 0
- Write `df_norm` at `startrow = len(df_raw) + 4`, title at row `len(df_raw) + 3`
- Write title strings directly to the openpyxl worksheet via `writer.sheets["Summary"]`

### Test coverage

**`tests/test_config.py`**
- `test_load_config_isotope_analysis_with_volume` — `volume=10.0` parsed correctly
- `test_load_config_isotope_analysis_volume_default` — absent → defaults to `1.0`

**`tests/test_isotope_analysis.py`**
- `test_summary_sheet_is_last_sheet` — `"Summary"` exists and is the last sheet name
- `test_summary_sheet_bq_values` — Bq values in summary match the source combo data
- `test_summary_sheet_normalized_values` — Bq/cm³ = Bq / volume
- `test_summary_sheet_empty_when_no_data` — no `"Summary"` sheet when `summary_rows` is empty
- `test_tdecay_s_not_in_combo_sheets` — `_tdecay_s` column absent from per-combo sheets
