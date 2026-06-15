# Isotope Analysis — Summary Sheet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `"Summary"` sheet to the isotope analysis Excel output that shows all combos × cooling times in two stacked flat tables — absolute Bq and Bq/cm³ normalized by a user-configured volume.

**Architecture:** Three focused changes to two files: `IsotopeConfig` gains a `volume` field; `read_resnuclei_file` gains an internal `_tdecay_s` sort-key field; and `run_isotope_analysis` is extended to accumulate summary rows and call a new `_build_summary_sheet` helper that writes the two-table layout using pandas `startrow` offsets and the openpyxl worksheet API for title rows.

**Tech Stack:** Python 3.11+, `pandas`, `openpyxl`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `grid_search/config.py` | Modify | Add `volume: float = 1.0` to `IsotopeConfig` |
| `grid_search/isotope_analysis.py` | Modify | Add `_tdecay_s` to row dict; update `run_isotope_analysis`; add `_build_summary_sheet` |
| `tests/test_config.py` | Modify | Two new tests for `volume` parsing |
| `tests/test_isotope_analysis.py` | Modify | Update existing mock; add 4 new tests |

---

## Task 1: Add `volume` to `IsotopeConfig`

**Files:**
- Modify: `grid_search/config.py:29-60`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_load_config_isotope_analysis_with_volume():
    raw = {
        **RAW,
        "isotope_analysis": {
            "isotopes": {27: 60},
            "rnc_files": ["merged_21"],
            "volume": 10.0,
        },
    }
    cfg = load_config(raw)
    assert cfg.isotope_analysis.volume == pytest.approx(10.0)


def test_load_config_isotope_analysis_volume_default():
    raw = {
        **RAW,
        "isotope_analysis": {
            "isotopes": {27: 60},
            "rnc_files": ["merged_21"],
        },
    }
    cfg = load_config(raw)
    assert cfg.isotope_analysis.volume == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/tonyf/Work/fluka-grid-search && python -m pytest tests/test_config.py -v -k "volume"
```

Expected: `AttributeError: 'IsotopeConfig' object has no attribute 'volume'`

- [ ] **Step 3: Add `volume` to `IsotopeConfig` and `load_config`**

In `grid_search/config.py`, change `IsotopeConfig` from:

```python
@dataclass
class IsotopeConfig:
    isotopes: dict[int, int]
    rnc_files: list[str]
    output: str = "isotopes.xlsx"
```

To:

```python
@dataclass
class IsotopeConfig:
    isotopes: dict[int, int]
    rnc_files: list[str]
    output: str = "isotopes.xlsx"
    volume: float = 1.0
```

In `load_config`, change the `IsotopeConfig(...)` construction from:

```python
        isotope_analysis = IsotopeConfig(
            isotopes={int(k): int(v) for k, v in ia_raw["isotopes"].items()},
            rnc_files=list(ia_raw["rnc_files"]),
            output=ia_raw.get("output", "isotopes.xlsx"),
        )
```

To:

```python
        isotope_analysis = IsotopeConfig(
            isotopes={int(k): int(v) for k, v in ia_raw["isotopes"].items()},
            rnc_files=list(ia_raw["rnc_files"]),
            output=ia_raw.get("output", "isotopes.xlsx"),
            volume=float(ia_raw.get("volume", 1.0)),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/tonyf/Work/fluka-grid-search && python -m pytest tests/test_config.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/tonyf/Work/fluka-grid-search && git add grid_search/config.py tests/test_config.py && git commit -m "feat: add volume field to IsotopeConfig"
```

---

## Task 2: Add `_tdecay_s` to `read_resnuclei_file` + strip from combo sheets

**Files:**
- Modify: `grid_search/isotope_analysis.py:100-141`
- Modify: `tests/test_isotope_analysis.py`

`_tdecay_s` is an internal sort key (cooling time in seconds as a float) stored in the row dict returned by `read_resnuclei_file`. It is used by the summary sheet for chronological ordering. The underscore prefix signals it is not for display — it is stripped before per-combo DataFrames are written to Excel.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_isotope_analysis.py`:

```python
def test_tdecay_s_not_in_combo_sheets(tmp_path):
    ia = IsotopeConfig(isotopes={27: 60}, rnc_files=["merged_21"])
    config = MagicMock()
    config.isotope_analysis = ia

    state = StateManager(tmp_path / "state.json")
    state.data = {"beame0.05_matGALLIUM": {"parameters": {}, "runs": {}}}

    fake_row = {
        "_tdecay_s": 86400.0,
        "CoolingTime": "1.0 d",
        "Parameters": "",
        "Co-60 (Bq)": 1000.0,
        "Co-60 (% Error)": 5.0,
        "Co-60 (µg)": 0.42,
    }

    with patch("grid_search.isotope_analysis.read_resnuclei_file", return_value=fake_row):
        run_isotope_analysis(tmp_path, config, state)

    df = pd.read_excel(tmp_path / "isotopes.xlsx", sheet_name="beame0.05_matGALLIUM")
    assert "_tdecay_s" not in df.columns
```

- [ ] **Step 2: Run test to confirm baseline**

```bash
cd /Users/tonyf/Work/fluka-grid-search && python -m pytest tests/test_isotope_analysis.py::test_tdecay_s_not_in_combo_sheets -v
```

This test currently passes (column doesn't exist yet). Confirm it passes, then proceed — it will catch any future regression.

- [ ] **Step 3: Add `_tdecay_s` to `read_resnuclei_file`**

In `grid_search/isotope_analysis.py`, change the `row` dict construction at line 102 from:

```python
    row: dict = {
        "CoolingTime": format_decay_time(tdecay_s),
        "Parameters": " ".join(f"{k}={v}" for k, v in params.items()),
    }
```

To:

```python
    row: dict = {
        "_tdecay_s": tdecay_s,
        "CoolingTime": format_decay_time(tdecay_s),
        "Parameters": " ".join(f"{k}={v}" for k, v in params.items()),
    }
```

- [ ] **Step 4: Strip `_tdecay_s` in `run_isotope_analysis`**

In `grid_search/isotope_analysis.py`, change line 141 from:

```python
            sheets[combo_name[:31]] = pd.DataFrame(rows)
```

To:

```python
            sheets[combo_name[:31]] = pd.DataFrame(rows).drop(columns=["_tdecay_s"], errors="ignore")
```

- [ ] **Step 5: Update the existing mock in `test_run_isotope_analysis_writes_excel`**

In `tests/test_isotope_analysis.py`, find `test_run_isotope_analysis_writes_excel`. Its `fake_row` is missing `_tdecay_s`. Add it so the mock reflects what `read_resnuclei_file` now returns:

```python
    fake_row = {
        "_tdecay_s": 86400.0,
        "CoolingTime": "1.0 d",
        "Parameters": "beame=0.05 mat=GALLIUM",
        "Co-60 (Bq)": 1000.0,
        "Co-60 (% Error)": 5.0,
        "Co-60 (µg)": 0.42,
    }
```

- [ ] **Step 6: Run all tests to verify they pass**

```bash
cd /Users/tonyf/Work/fluka-grid-search && python -m pytest tests/test_isotope_analysis.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/tonyf/Work/fluka-grid-search && git add grid_search/isotope_analysis.py tests/test_isotope_analysis.py && git commit -m "feat: add _tdecay_s sort key to resnuclei row, strip from combo sheets"
```

---

## Task 3: Add `_build_summary_sheet` and wire into `run_isotope_analysis`

**Files:**
- Modify: `grid_search/isotope_analysis.py`
- Modify: `tests/test_isotope_analysis.py`

This task adds the summary sheet. `run_isotope_analysis` accumulates `summary_rows` (with expanded parameter columns) alongside the per-combo rows, then calls `_build_summary_sheet` inside the same `ExcelWriter` context to write the `"Summary"` sheet last.

The sheet layout (for n data rows in the raw table):

```
Sheet row 1  : "Activity (Bq)"                                  ← openpyxl ws.cell(row=1)
Sheet row 2  : [CoolingTime | beame | … | Co-60 (Bq)]           ← df_raw header (startrow=1)
Sheet rows 3…n+2 : data rows
Sheet row n+4: "Normalized Activity (Bq/cm³) — volume: X cm³"   ← openpyxl ws.cell(row=n+4)
Sheet row n+5: [CoolingTime | beame | … | Co-60 (Bq/cm³)]       ← df_norm header (startrow=n+4)
Sheet rows n+6…: normalized data rows
```

Note: `startrow` in `DataFrame.to_excel` is 0-indexed; `ws.cell(row=…)` is 1-indexed. A title written at openpyxl row R sits at pandas row index R-1, which is one row above the DataFrame header written at `startrow=R-1`. This means: title at `ws.cell(row=1)` + `df_raw.to_excel(startrow=1)` puts the title in sheet row 1 and the header in sheet row 2.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_isotope_analysis.py`:

```python
def test_summary_sheet_is_last_sheet(tmp_path):
    ia = IsotopeConfig(isotopes={27: 60}, rnc_files=["merged_21"], volume=5.0)
    config = MagicMock()
    config.isotope_analysis = ia

    state = StateManager(tmp_path / "state.json")
    state.data = {"beame0.05_matGALLIUM": {"parameters": {"beame": 0.05}, "runs": {}}}

    fake_row = {
        "_tdecay_s": 86400.0,
        "CoolingTime": "1.0 d",
        "Parameters": "beame=0.05",
        "Co-60 (Bq)": 1000.0,
        "Co-60 (% Error)": 5.0,
        "Co-60 (µg)": 0.42,
    }

    with patch("grid_search.isotope_analysis.read_resnuclei_file", return_value=fake_row):
        run_isotope_analysis(tmp_path, config, state)

    xl = pd.ExcelFile(tmp_path / "isotopes.xlsx")
    assert xl.sheet_names[-1] == "Summary"


def test_summary_sheet_bq_values(tmp_path):
    ia = IsotopeConfig(isotopes={27: 60}, rnc_files=["merged_21"], volume=5.0)
    config = MagicMock()
    config.isotope_analysis = ia

    state = StateManager(tmp_path / "state.json")
    state.data = {"beame0.05_matGALLIUM": {"parameters": {"beame": 0.05}, "runs": {}}}

    fake_row = {
        "_tdecay_s": 86400.0,
        "CoolingTime": "1.0 d",
        "Parameters": "beame=0.05",
        "Co-60 (Bq)": 1000.0,
        "Co-60 (% Error)": 5.0,
        "Co-60 (µg)": 0.42,
    }

    with patch("grid_search.isotope_analysis.read_resnuclei_file", return_value=fake_row):
        run_isotope_analysis(tmp_path, config, state)

    # Activity (Bq) title at sheet row 1; DataFrame header at sheet row 2 = pandas header index 1
    df = pd.read_excel(tmp_path / "isotopes.xlsx", sheet_name="Summary", header=1)
    assert "Co-60 (Bq)" in df.columns
    assert df["Co-60 (Bq)"].iloc[0] == pytest.approx(1000.0)
    assert "beame" in df.columns
    assert df["beame"].iloc[0] == pytest.approx(0.05)


def test_summary_sheet_normalized_values(tmp_path):
    ia = IsotopeConfig(isotopes={27: 60}, rnc_files=["merged_21"], volume=5.0)
    config = MagicMock()
    config.isotope_analysis = ia

    state = StateManager(tmp_path / "state.json")
    state.data = {"beame0.05_matGALLIUM": {"parameters": {"beame": 0.05}, "runs": {}}}

    fake_row = {
        "_tdecay_s": 86400.0,
        "CoolingTime": "1.0 d",
        "Parameters": "beame=0.05",
        "Co-60 (Bq)": 1000.0,
        "Co-60 (% Error)": 5.0,
        "Co-60 (µg)": 0.42,
    }

    with patch("grid_search.isotope_analysis.read_resnuclei_file", return_value=fake_row):
        run_isotope_analysis(tmp_path, config, state)

    # Find the "Normalized" title row, read the table immediately below it
    df_full = pd.read_excel(
        tmp_path / "isotopes.xlsx", sheet_name="Summary", header=None
    )
    norm_title_idx = df_full[
        df_full.iloc[:, 0].astype(str).str.contains("Normalized", na=False)
    ].index[0]
    df_norm = pd.read_excel(
        tmp_path / "isotopes.xlsx", sheet_name="Summary", header=norm_title_idx + 1
    )
    assert "Co-60 (Bq/cm³)" in df_norm.columns
    assert df_norm["Co-60 (Bq/cm³)"].iloc[0] == pytest.approx(200.0)  # 1000.0 / 5.0


def test_summary_sheet_absent_when_no_data(tmp_path):
    ia = IsotopeConfig(isotopes={27: 60}, rnc_files=["merged_21"])
    config = MagicMock()
    config.isotope_analysis = ia

    state = StateManager(tmp_path / "state.json")
    state.data = {"beame0.05_matGALLIUM": {"parameters": {}, "runs": {}}}

    with patch("grid_search.isotope_analysis.read_resnuclei_file", return_value=None):
        run_isotope_analysis(tmp_path, config, state)

    assert not (tmp_path / "isotopes.xlsx").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/tonyf/Work/fluka-grid-search && python -m pytest tests/test_isotope_analysis.py -v -k "summary"
```

Expected: `AssertionError` — `"Summary"` sheet does not exist yet.

- [ ] **Step 3: Append `_build_summary_sheet` to `grid_search/isotope_analysis.py`**

Add at the end of `grid_search/isotope_analysis.py`:

```python
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
```

- [ ] **Step 4: Replace `run_isotope_analysis` in `grid_search/isotope_analysis.py`**

Replace the entire `run_isotope_analysis` function with:

```python
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
```

- [ ] **Step 5: Run the full test suite**

```bash
cd /Users/tonyf/Work/fluka-grid-search && python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/tonyf/Work/fluka-grid-search && git add grid_search/isotope_analysis.py tests/test_isotope_analysis.py && git commit -m "feat: add Summary sheet with Bq and Bq/cm3 tables to isotope analysis"
```

---

## Spec Coverage Checklist

| Spec requirement | Task |
|---|---|
| `volume` field in `IsotopeConfig` + YAML parsing | 1 |
| `_tdecay_s` sort key in `read_resnuclei_file` | 2 |
| `_tdecay_s` stripped from per-combo sheets | 2 |
| `_build_summary_sheet` with two stacked tables | 3 |
| Rows sorted by cooling time then combo | 3 |
| Parameters as individual columns (not combined string) | 3 |
| Only Bq columns in summary (not % Error or µg) | 3 |
| Bq/cm³ = Bq / volume | 3 |
| `"Summary"` is last sheet | 3 |
| No Summary sheet when no data | 3 |
