# Isotope Pivot Sheet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Pivot" sheet to `isotopes.xlsx` that lays out isotope activities as a cross-tab — grid parameters as nested column headers, isotopes × cooling times as rows — with an optional grouping parameter that splits the table into one block per group value.

**Architecture:** A single new function `_build_pivot_sheet` in `isotope_analysis.py` melts `summary_rows` to long form, pivots to a pandas MultiIndex DataFrame, and writes two blocks (Bq and Bq/cm³) per group to the "Pivot" sheet using the existing `pd.ExcelWriter`. A new optional `pivot_group_by` field in `IsotopeConfig` names the parameter used as the table-level grouper.

**Tech Stack:** Python, pandas (melt + pivot_table + to_excel), openpyxl (cell writes for title rows)

---

## File Map

| File | Change |
|---|---|
| `grid_search/config.py` | Add `pivot_group_by: Optional[str] = None` to `IsotopeConfig`; read from yaml in `load_config` |
| `grid_search/isotope_analysis.py` | Add `_build_pivot_sheet`; call it from `run_isotope_analysis` |
| `tests/test_config.py` | Test that `pivot_group_by` loads correctly |
| `tests/test_isotope_analysis.py` | Unit tests for `_build_pivot_sheet`; integration test for Pivot sheet; fix existing tests to set `config.grid.parameters` |

---

### Task 1: Add `pivot_group_by` to `IsotopeConfig` and `load_config`

**Files:**
- Modify: `grid_search/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_isotope_config_pivot_group_by_defaults_to_none():
    raw = {
        **RAW,
        "isotope_analysis": {
            "isotopes": {"27": "60"},
            "rnc_files": ["merged_21"],
        },
    }
    cfg = load_config(raw)
    assert cfg.isotope_analysis.pivot_group_by is None


def test_isotope_config_pivot_group_by_loaded():
    raw = {
        **RAW,
        "isotope_analysis": {
            "isotopes": {"27": "60"},
            "rnc_files": ["merged_21"],
            "pivot_group_by": "mat",
        },
    }
    cfg = load_config(raw)
    assert cfg.isotope_analysis.pivot_group_by == "mat"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/tonyf/Work/fluka-grid-search
pytest tests/test_config.py::test_isotope_config_pivot_group_by_defaults_to_none tests/test_config.py::test_isotope_config_pivot_group_by_loaded -v
```

Expected: `AttributeError: 'IsotopeConfig' object has no attribute 'pivot_group_by'`

- [ ] **Step 3: Add field to `IsotopeConfig` and `load_config`**

In `grid_search/config.py`, update `IsotopeConfig`:

```python
@dataclass
class IsotopeConfig:
    isotopes: dict[int, int]
    rnc_files: list[str]
    output: str = "isotopes.xlsx"
    volume: float = 1.0
    pivot_group_by: Optional[str] = None
```

In `load_config`, update the `IsotopeConfig(...)` constructor call:

```python
        isotope_analysis = IsotopeConfig(
            isotopes={int(k): int(v) for k, v in ia_raw["isotopes"].items()},
            rnc_files=list(ia_raw["rnc_files"]),
            output=ia_raw.get("output", "isotopes.xlsx"),
            volume=float(ia_raw.get("volume", 1.0)),
            pivot_group_by=ia_raw.get("pivot_group_by"),
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_config.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add grid_search/config.py tests/test_config.py
git commit -m "feat: add pivot_group_by field to IsotopeConfig"
```

---

### Task 2: Write failing unit tests for `_build_pivot_sheet`

**Files:**
- Test: `tests/test_isotope_analysis.py`

The function does not exist yet — importing it causes `ImportError`, which is the failing state.

- [ ] **Step 1: Add import and tests**

Add to `tests/test_isotope_analysis.py` (after existing imports at top):

```python
from grid_search.isotope_analysis import _build_pivot_sheet
from openpyxl import load_workbook
```

Then add these test functions at the bottom of the file:

```python
def _make_summary_rows_simple():
    """2 isotopes, 2 cooling times, 2 beame values — no grouping param."""
    return [
        {"_tdecay_s": 0.0,     "CoolingTime": "0 s", "beame": 0.1, "Co-60 (Bq)": 100.0, "H-3 (Bq)": 10.0},
        {"_tdecay_s": 86400.0, "CoolingTime": "1 d", "beame": 0.1, "Co-60 (Bq)": 80.0,  "H-3 (Bq)": 8.0},
        {"_tdecay_s": 0.0,     "CoolingTime": "0 s", "beame": 0.5, "Co-60 (Bq)": 200.0, "H-3 (Bq)": 20.0},
        {"_tdecay_s": 86400.0, "CoolingTime": "1 d", "beame": 0.5, "Co-60 (Bq)": 160.0, "H-3 (Bq)": 16.0},
    ]


def test_build_pivot_sheet_creates_pivot_sheet(tmp_path):
    output = tmp_path / "pivot_test.xlsx"
    with pd.ExcelWriter(str(output), engine="openpyxl") as writer:
        _build_pivot_sheet(
            writer,
            summary_rows=_make_summary_rows_simple(),
            param_names=["beame"],
            group_by=None,
            volume=2.0,
        )

    wb = load_workbook(output)
    assert "Pivot" in wb.sheetnames


def test_build_pivot_sheet_bq_values_present(tmp_path):
    output = tmp_path / "pivot_test.xlsx"
    with pd.ExcelWriter(str(output), engine="openpyxl") as writer:
        _build_pivot_sheet(
            writer,
            summary_rows=_make_summary_rows_simple(),
            param_names=["beame"],
            group_by=None,
            volume=2.0,
        )

    wb = load_workbook(output)
    ws = wb["Pivot"]
    flat = [cell.value for row in ws.iter_rows() for cell in row]
    assert 100.0 in flat   # Co-60 Bq at beame=0.1, 0 s
    assert 200.0 in flat   # Co-60 Bq at beame=0.5, 0 s


def test_build_pivot_sheet_normalized_values_present(tmp_path):
    output = tmp_path / "pivot_test.xlsx"
    with pd.ExcelWriter(str(output), engine="openpyxl") as writer:
        _build_pivot_sheet(
            writer,
            summary_rows=_make_summary_rows_simple(),
            param_names=["beame"],
            group_by=None,
            volume=2.0,
        )

    wb = load_workbook(output)
    ws = wb["Pivot"]
    flat = [cell.value for row in ws.iter_rows() for cell in row]
    # 100.0 / 2.0 = 50.0 and 200.0 / 2.0 = 100.0
    assert any(abs(v - 50.0) < 1e-6 for v in flat if isinstance(v, float))
    assert any(abs(v - 100.0) < 1e-6 for v in flat if isinstance(v, float))


def test_build_pivot_sheet_title_row(tmp_path):
    output = tmp_path / "pivot_test.xlsx"
    with pd.ExcelWriter(str(output), engine="openpyxl") as writer:
        _build_pivot_sheet(
            writer,
            summary_rows=_make_summary_rows_simple(),
            param_names=["beame"],
            group_by=None,
            volume=2.0,
        )

    wb = load_workbook(output)
    ws = wb["Pivot"]
    assert ws.cell(row=1, column=1).value == "Activity (Bq)"


def test_build_pivot_sheet_cooling_time_order(tmp_path):
    """0 s must appear before 1 d in the sheet regardless of input order."""
    rows_reversed = [
        {"_tdecay_s": 86400.0, "CoolingTime": "1 d", "beame": 0.1, "Co-60 (Bq)": 80.0},
        {"_tdecay_s": 0.0,     "CoolingTime": "0 s", "beame": 0.1, "Co-60 (Bq)": 100.0},
    ]
    output = tmp_path / "pivot_order.xlsx"
    with pd.ExcelWriter(str(output), engine="openpyxl") as writer:
        _build_pivot_sheet(
            writer,
            summary_rows=rows_reversed,
            param_names=["beame"],
            group_by=None,
            volume=1.0,
        )

    wb = load_workbook(output)
    ws = wb["Pivot"]
    # CoolingTime values are in column 2 (index level 1)
    col2 = [ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)]
    idx_zero = next((i for i, v in enumerate(col2) if v == "0 s"), None)
    idx_one  = next((i for i, v in enumerate(col2) if v == "1 d"), None)
    assert idx_zero is not None and idx_one is not None
    assert idx_zero < idx_one


def test_build_pivot_sheet_empty_rows_does_nothing(tmp_path):
    output = tmp_path / "pivot_empty.xlsx"
    with pd.ExcelWriter(str(output), engine="openpyxl") as writer:
        pd.DataFrame({"x": [1]}).to_excel(writer, sheet_name="dummy", index=False)
        _build_pivot_sheet(
            writer,
            summary_rows=[],
            param_names=["beame"],
            group_by=None,
            volume=1.0,
        )

    wb = load_workbook(output)
    assert "Pivot" not in wb.sheetnames


def test_build_pivot_sheet_group_by_titles(tmp_path):
    rows = [
        {"_tdecay_s": 0.0, "CoolingTime": "0 s", "mat": "GALLIUM",  "beame": 0.5, "Co-60 (Bq)": 100.0},
        {"_tdecay_s": 0.0, "CoolingTime": "0 s", "mat": "TUNGSTEN", "beame": 0.5, "Co-60 (Bq)": 50.0},
    ]
    output = tmp_path / "pivot_grouped.xlsx"
    with pd.ExcelWriter(str(output), engine="openpyxl") as writer:
        _build_pivot_sheet(
            writer,
            summary_rows=rows,
            param_names=["mat", "beame"],
            group_by="mat",
            volume=1.0,
        )

    wb = load_workbook(output)
    ws = wb["Pivot"]
    flat = [cell.value for row in ws.iter_rows() for cell in row]
    assert "mat=GALLIUM" in flat
    assert "mat=TUNGSTEN" in flat


def test_build_pivot_sheet_group_by_values(tmp_path):
    rows = [
        {"_tdecay_s": 0.0, "CoolingTime": "0 s", "mat": "GALLIUM",  "beame": 0.5, "Co-60 (Bq)": 100.0},
        {"_tdecay_s": 0.0, "CoolingTime": "0 s", "mat": "TUNGSTEN", "beame": 0.5, "Co-60 (Bq)": 50.0},
    ]
    output = tmp_path / "pivot_grouped_vals.xlsx"
    with pd.ExcelWriter(str(output), engine="openpyxl") as writer:
        _build_pivot_sheet(
            writer,
            summary_rows=rows,
            param_names=["mat", "beame"],
            group_by="mat",
            volume=1.0,
        )

    wb = load_workbook(output)
    ws = wb["Pivot"]
    flat = [cell.value for row in ws.iter_rows() for cell in row]
    assert 100.0 in flat
    assert 50.0 in flat
```

- [ ] **Step 2: Run tests to confirm they fail with ImportError**

```bash
pytest tests/test_isotope_analysis.py::test_build_pivot_sheet_creates_pivot_sheet -v
```

Expected: `ImportError: cannot import name '_build_pivot_sheet'`

---

### Task 3: Implement `_build_pivot_sheet`

**Files:**
- Modify: `grid_search/isotope_analysis.py`

- [ ] **Step 1: Add `_build_pivot_sheet` after `_build_summary_sheet`**

```python
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
```

- [ ] **Step 2: Run pivot unit tests**

```bash
pytest tests/test_isotope_analysis.py -k "pivot_sheet" -v
```

Expected: all 8 pivot tests pass.

- [ ] **Step 3: Run full suite for regressions**

```bash
pytest tests/ -v
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add grid_search/isotope_analysis.py tests/test_isotope_analysis.py
git commit -m "feat: add _build_pivot_sheet for cross-tab isotope activity"
```

---

### Task 4: Wire `_build_pivot_sheet` into `run_isotope_analysis` and fix existing tests

**Files:**
- Modify: `grid_search/isotope_analysis.py`
- Modify: `tests/test_isotope_analysis.py`

Existing tests pass `config = MagicMock()` without setting `config.grid.parameters`. The new call `list(config.grid.parameters.keys())` will receive a MagicMock, which breaks the melt step. Every test that calls `run_isotope_analysis` must set `config.grid.parameters` to a real dict.

- [ ] **Step 1: Write integration test for the Pivot sheet**

Add to `tests/test_isotope_analysis.py`:

```python
def test_pivot_sheet_is_written(tmp_path):
    ia = IsotopeConfig(isotopes={27: 60}, rnc_files=["merged_21"], volume=5.0)
    config = MagicMock()
    config.isotope_analysis = ia
    config.grid.parameters = {"beame": [0.05, 0.5]}

    state = StateManager(tmp_path / "state.json")
    state.data = {
        "beame0.05": {"parameters": {"beame": 0.05}, "runs": {}},
        "beame0.5":  {"parameters": {"beame": 0.5},  "runs": {}},
    }

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
    assert "Pivot" in xl.sheet_names
```

- [ ] **Step 2: Run the new test to confirm it fails**

```bash
pytest tests/test_isotope_analysis.py::test_pivot_sheet_is_written -v
```

Expected: fails because `_build_pivot_sheet` is not yet called from `run_isotope_analysis`.

- [ ] **Step 3: Update `run_isotope_analysis`**

In `grid_search/isotope_analysis.py`, update the `with pd.ExcelWriter(...)` block:

```python
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
```

- [ ] **Step 4: Fix existing `run_isotope_analysis` tests — add `config.grid.parameters`**

In `tests/test_isotope_analysis.py`, add `config.grid.parameters = {...}` to each test below.

**`test_run_isotope_analysis_writes_excel`** — parameters match the combo:
```python
    config.grid.parameters = {"beame": [0.05], "mat": ["GALLIUM"]}
```

**`test_run_isotope_analysis_no_files_prints_warning`**:
```python
    config.grid.parameters = {}
```

**`test_run_isotope_analysis_combo_filter`**:
```python
    config.grid.parameters = {}
```

**`test_tdecay_s_not_in_combo_sheets`**:
```python
    config.grid.parameters = {}
```

**`test_summary_sheet_is_last_sheet`** — also update assertion (Pivot is now the last sheet):
```python
    config.grid.parameters = {"beame": [0.05]}
    # ...
    xl = pd.ExcelFile(tmp_path / "isotopes.xlsx")
    assert "Summary" in xl.sheet_names
    assert xl.sheet_names[-1] == "Pivot"
```

**`test_summary_sheet_bq_values`**:
```python
    config.grid.parameters = {"beame": [0.05]}
```

**`test_summary_sheet_normalized_values`**:
```python
    config.grid.parameters = {"beame": [0.05]}
```

**`test_summary_sheet_absent_when_no_data`**:
```python
    config.grid.parameters = {}
```

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add grid_search/isotope_analysis.py tests/test_isotope_analysis.py
git commit -m "feat: wire _build_pivot_sheet into run_isotope_analysis"
```
