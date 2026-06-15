# Isotope Analysis Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--analyze` flag to `run_grid.py` that reads merged RESNUCLEI binary files from each combo's `postproc/` directory, extracts user-specified isotopes, and writes a structured Excel report with one sheet per parameter combination.

**Architecture:** A standalone FORTRAN binary reader (`grid_search/resnuclei.py`) is extracted from `docs/references/flair_libs/`, keeping only the `Resnuclei` class and its helpers. The analysis logic (`grid_search/isotope_analysis.py`) uses `periodictable` + `radioactivedecay` for isotope metadata and `pandas`/`openpyxl` for Excel output. The config is extended with an optional `isotope_analysis` section; `run_grid.py` gains a `--analyze` flag.

**Tech Stack:** Python 3.11+, `periodictable`, `radioactivedecay`, `pandas`, `openpyxl`, `numpy`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `pyproject.toml` | Modify | Add new runtime dependencies |
| `grid_search/resnuclei.py` | Create | FORTRAN binary reader for RESNUCLEI files |
| `grid_search/config.py` | Modify | Add `IsotopeConfig` dataclass |
| `grid_search/isotope_analysis.py` | Create | Analysis logic: isotope lookup, extraction, Excel output |
| `run_grid.py` | Modify | Add `--analyze` flag and `_do_analyze()` |
| `tests/test_resnuclei.py` | Create | Tests for FORTRAN reader |
| `tests/test_isotope_analysis.py` | Create | Tests for analysis functions |
| `tests/test_config.py` | Modify | Tests for `IsotopeConfig` parsing |
| `tests/test_run_grid.py` | Modify | Tests for `--analyze` flag |

---

## Task 1: Add dependencies to `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

No tests needed — verify with `pip install -e ".[dev]"`.

- [ ] **Step 1: Update `pyproject.toml` dependencies**

Replace the `dependencies` list in `pyproject.toml`:

```toml
[project]
name = "fluka-grid-search"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pyyaml>=6.0",
    "pandas>=2.0",
    "openpyxl>=3.1",
    "periodictable>=1.6",
    "radioactivedecay>=0.4",
    "numpy>=1.24",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]
```

- [ ] **Step 2: Install dependencies**

```bash
pip install -e ".[dev]"
```

Expected: all packages install without error.

- [ ] **Step 3: Verify imports work**

```bash
python -c "import pandas; import periodictable; import radioactivedecay; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pandas, openpyxl, periodictable, radioactivedecay deps"
```

---

## Task 2: `grid_search/resnuclei.py` — FORTRAN binary reader

**Files:**
- Create: `grid_search/resnuclei.py`
- Create: `tests/test_resnuclei.py`

This refactors `docs/references/flair_libs/Data.py` + `fortran.py` into a single focused module. Only `Resnuclei` and its dependencies are kept — no `Usrbin`, no `bmath`, no `plot`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resnuclei.py`:

```python
import io
import struct
import pytest
from grid_search.resnuclei import fortran_read, fortran_skip, unpack_array, Detector


def make_block(payload: bytes) -> bytes:
    size = len(payload)
    header = struct.pack("=i", size)
    return header + payload + header


def test_fortran_read_returns_payload():
    payload = b"hello world!"
    f = io.BytesIO(make_block(payload))
    assert fortran_read(f) == payload


def test_fortran_read_eof_returns_none():
    f = io.BytesIO(b"")
    assert fortran_read(f) is None


def test_fortran_skip_skips_first_reads_second():
    block1 = make_block(b"first_block_")
    block2 = make_block(b"second_block")
    f = io.BytesIO(block1 + block2)
    size = fortran_skip(f)
    assert size == 12
    assert fortran_read(f) == b"second_block"


def test_unpack_array():
    data = struct.pack("=3f", 1.0, 2.0, 3.0)
    result = unpack_array(data)
    assert len(result) == 3
    assert result[0] == pytest.approx(1.0)
    assert result[1] == pytest.approx(2.0)
    assert result[2] == pytest.approx(3.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_resnuclei.py -v
```

Expected: `ModuleNotFoundError: No module named 'grid_search.resnuclei'`

- [ ] **Step 3: Create `grid_search/resnuclei.py`**

```python
from __future__ import annotations
import struct
from dataclasses import dataclass
from typing import Optional


def fortran_read(f) -> Optional[bytes]:
    blen = f.read(4)
    if not blen:
        return None
    (size,) = struct.unpack("=i", blen)
    data = f.read(size)
    blen2 = f.read(4)
    if blen != blen2:
        raise IOError("Reading Fortran block")
    return data


def fortran_skip(f) -> int:
    blen = f.read(4)
    if not blen:
        return 0
    (size,) = struct.unpack("=i", blen)
    f.seek(size, 1)
    blen2 = f.read(4)
    if blen != blen2:
        raise IOError("Skipping Fortran block")
    return size


def unpack_array(data: bytes) -> tuple:
    return struct.unpack("=%df" % (len(data) // 4), data)


@dataclass
class Detector:
    num: int
    name: str
    volume: float = 0.0
    mhigh: int = 0
    zhigh: int = 0
    nmzmin: int = 0


class Resnuclei:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.title = ""
        self.time = ""
        self.weight = 0.0
        self.ncase = 0
        self.nbatch = 0
        self.detector: list[Detector] = []
        self.statpos = -1
        self.nisomers = 0
        self.evol = False
        self.tdecay: float | tuple = 0.0
        self._f = None
        self._read_header()

    def _open(self) -> None:
        self._f = open(self.filename, "rb")

    def _close(self) -> None:
        if self._f:
            self._f.close()
            self._f = None

    def _read_base_header(self) -> None:
        data = fortran_read(self._f)
        if data is None:
            raise IOError("Invalid file")
        size = len(data)
        over1b = 0
        if size == 116:
            (title, time, self.weight) = struct.unpack("=80s32sf", data)
            self.ncase = 1
            self.nbatch = 1
        elif size == 120:
            (title, time, self.weight, self.ncase) = struct.unpack("=80s32sfi", data)
            self.nbatch = 1
        elif size == 124:
            (title, time, self.weight, self.ncase, self.nbatch) = struct.unpack("=80s32sfii", data)
        elif size == 128:
            (title, time, self.weight, self.ncase, over1b, self.nbatch) = struct.unpack("=80s32sfiii", data)
        else:
            raise IOError(f"Invalid USRxxx header size={size}")
        if over1b > 0:
            self.ncase = self.ncase + over1b * 1_000_000_000
        self.title = title.strip().decode(errors="replace")
        self.time = time.strip().decode(errors="replace")

    def _read_header(self) -> None:
        self._open()
        self._read_base_header()
        if self.ncase <= 0:
            self.evol = True
            self.ncase = -self.ncase
            data = fortran_read(self._f)
            nir = (len(data) - 4) // 8
            struct.unpack("=i%df" % (2 * nir), data)
        else:
            self.evol = False

        for _ in range(1000):
            data = fortran_read(self._f)
            if data is None:
                break
            size = len(data)
            if size == 14:
                if data[:8] == b"ISOMERS:":
                    self.nisomers = struct.unpack("=10xi", data)[0]
                    fortran_read(self._f)
                    data = fortran_read(self._f)
                    size = len(data)
                if data[:10] == b"STATISTICS":
                    self.statpos = self._f.tell()
                    break
            elif size != 38:
                raise IOError(f"Invalid RESNUCLEi header size={size}")

            header = struct.unpack("=i10siif3i", data)
            det = Detector(
                num=header[0],
                name=header[1].strip().decode(errors="replace"),
                volume=header[4],
                mhigh=header[5],
                zhigh=header[6],
                nmzmin=header[7],
            )
            self.detector.append(det)

            if self.evol:
                data = fortran_read(self._f)
                self.tdecay = struct.unpack("=f", data)
            else:
                self.tdecay = 0.0

            size = det.zhigh * det.mhigh * 4
            if size != fortran_skip(self._f):
                raise IOError("Invalid RESNUCLEi file")
        self._close()

    def read_data(self, n: int) -> bytes:
        self._open()
        fortran_skip(self._f)
        if self.evol:
            fortran_skip(self._f)
        for _ in range(n):
            fortran_skip(self._f)
            if self.evol:
                fortran_skip(self._f)
            fortran_skip(self._f)
            if self.nisomers:
                fortran_skip(self._f)
                fortran_skip(self._f)
        fortran_skip(self._f)
        if self.evol:
            fortran_skip(self._f)
        data = fortran_read(self._f)
        self._close()
        return data

    def read_stat(self, n: int) -> Optional[tuple]:
        if self.statpos < 0:
            return None
        self._open()
        self._f.seek(self.statpos)
        nskip = 7 * n if self.nisomers else 6 * n
        for _ in range(nskip):
            fortran_skip(self._f)
        total = fortran_read(self._f)
        A = fortran_read(self._f)
        errA = fortran_read(self._f)
        Z = fortran_read(self._f)
        errZ = fortran_read(self._f)
        data = fortran_read(self._f)
        iso = fortran_read(self._f) if self.nisomers else None
        self._close()
        return (total, A, errA, Z, errZ, data, iso)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_resnuclei.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add grid_search/resnuclei.py tests/test_resnuclei.py
git commit -m "feat: add resnuclei FORTRAN binary reader"
```

---

## Task 3: Add `IsotopeConfig` to `grid_search/config.py`

**Files:**
- Modify: `grid_search/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_config.py`:

```python
from grid_search.config import IsotopeConfig


def test_load_config_with_isotope_analysis():
    raw = {
        **RAW,
        "isotope_analysis": {
            "isotopes": {27: 60, 55: 137},
            "rnc_files": ["merged_21", "merged_22"],
        },
    }
    cfg = load_config(raw)
    assert cfg.isotope_analysis is not None
    assert cfg.isotope_analysis.isotopes == {27: 60, 55: 137}
    assert cfg.isotope_analysis.rnc_files == ["merged_21", "merged_22"]
    assert cfg.isotope_analysis.output == "isotopes.xlsx"


def test_load_config_isotope_analysis_absent():
    cfg = load_config(RAW)
    assert cfg.isotope_analysis is None


def test_load_config_isotope_analysis_custom_output():
    raw = {
        **RAW,
        "isotope_analysis": {
            "isotopes": {27: 60},
            "rnc_files": ["merged_21"],
            "output": "my_report.xlsx",
        },
    }
    cfg = load_config(raw)
    assert cfg.isotope_analysis.output == "my_report.xlsx"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v -k "isotope"
```

Expected: `ImportError` or `AttributeError: 'Config' object has no attribute 'isotope_analysis'`

- [ ] **Step 3: Add `IsotopeConfig` to `grid_search/config.py`**

After the `ExecutionConfig` dataclass (around line 28), insert:

```python
@dataclass
class IsotopeConfig:
    isotopes: dict[int, int]
    rnc_files: list[str]
    output: str = "isotopes.xlsx"
```

Replace the `Config` dataclass to add the new optional field at the end:

```python
@dataclass
class Config:
    fluka: FlukaConfig
    output_dir: Path
    grid: GridConfig
    execution: ExecutionConfig
    postprocessing: dict[str, str]
    isotope_analysis: Optional[IsotopeConfig] = None
```

Replace the entire `load_config` function body with the version that parses `isotope_analysis`:

```python
def load_config(source: dict | Path) -> Config:
    if isinstance(source, Path):
        with open(source) as f:
            raw = yaml.safe_load(f)
    else:
        raw = source

    ia_raw = raw.get("isotope_analysis")
    isotope_analysis = None
    if ia_raw:
        isotope_analysis = IsotopeConfig(
            isotopes={int(k): int(v) for k, v in ia_raw["isotopes"].items()},
            rnc_files=list(ia_raw["rnc_files"]),
            output=ia_raw.get("output", "isotopes.xlsx"),
        )

    return Config(
        fluka=FlukaConfig(
            input=Path(raw["fluka"]["input"]),
            custom_executable=raw["fluka"].get("custom_executable"),
            rfluka_path=raw["fluka"].get("rfluka_path"),
            primaries=raw["fluka"].get("primaries"),
        ),
        output_dir=Path(raw["output"]["directory"]),
        grid=GridConfig(
            parameters=raw["grid"]["parameters"],
            runs_per_combo=raw["grid"]["runs_per_combo"],
        ),
        execution=ExecutionConfig(
            max_parallel=raw["execution"]["max_parallel"],
        ),
        postprocessing={
            ext: v["executable"]
            for ext, v in raw.get("postprocessing", {}).items()
        },
        isotope_analysis=isotope_analysis,
    )
```

- [ ] **Step 4: Run all config tests**

```bash
pytest tests/test_config.py -v
```

Expected: all tests PASS (including the 3 new ones).

- [ ] **Step 5: Commit**

```bash
git add grid_search/config.py tests/test_config.py
git commit -m "feat: add IsotopeConfig dataclass and config parsing"
```

---

## Task 4: Create `grid_search/isotope_analysis.py` with pure functions

**Files:**
- Create: `grid_search/isotope_analysis.py`
- Create: `tests/test_isotope_analysis.py`

These five pure functions have no file I/O — they are helpers used by the extraction functions in Tasks 5 and 6.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_isotope_analysis.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_isotope_analysis.py -v
```

Expected: `ModuleNotFoundError: No module named 'grid_search.isotope_analysis'`

- [ ] **Step 3: Create `grid_search/isotope_analysis.py` with pure functions**

```python
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
    except Exception:
        return 0.0


def half_life(z: int, a: int) -> float:
    try:
        nuc = rd.Nuclide(isotope_symbol(z, a))
        hl = nuc.half_life()
        return float(hl) if hl is not None else 0.0
    except Exception:
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
        return f"{int(seconds)} s"
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_isotope_analysis.py -v
```

Expected: 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add grid_search/isotope_analysis.py tests/test_isotope_analysis.py
git commit -m "feat: add isotope_analysis pure functions"
```

---

## Task 5: Add `read_resnuclei_file` to `grid_search/isotope_analysis.py`

**Files:**
- Modify: `grid_search/isotope_analysis.py`
- Modify: `tests/test_isotope_analysis.py`

This function opens one merged file, extracts the 2D (Z, A) activity array, filters to requested isotopes, and returns a single row dict with Bq, % Error, and µg columns.

**Extraction algorithm** (from `docs/references/isotopes.py`, canonical):
- `amax = 2 * zhigh + mhigh + nmzmin`
- For each `a` in `[1, amax]` and `z` in `[0, zhigh)`: `m = a - 2*z - nmzmin - 3`
- If `0 <= m < mhigh`: `pos = z + m * zhigh`, `Bq = fdata[pos] * volume`, `BqErr = edata[pos] * fdata[pos] * volume`
- Actual Z = `z + 1`, actual A = `a`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_isotope_analysis.py`:

```python
import struct
from unittest.mock import patch, MagicMock
from grid_search.isotope_analysis import read_resnuclei_file
from grid_search.resnuclei import Detector


def make_float_bytes(*values):
    return struct.pack(f"={len(values)}f", *values)


def test_missing_rnc_file_is_skipped(tmp_path):
    row = read_resnuclei_file(
        path=tmp_path / "nonexistent",
        requested_isotopes={27: 60},
        params={},
    )
    assert row is None


def test_read_resnuclei_file_returns_known_isotope(tmp_path):
    # Detector: zhigh=2, mhigh=2, nmzmin=0, volume=2.0
    # For Z=1 (z=0), A=3: m = 3 - 2*0 - 0 - 3 = 0, pos = 0 + 0*2 = 0
    # Bq = fdata[0] * volume = 100.0 * 2.0 = 200.0
    # BqErr = edata[0] * fdata[0] * volume = 0.05 * 100.0 * 2.0 = 10.0
    # % Error = (10.0 / 200.0) * 100 = 5.0

    det = Detector(num=1, name="test", volume=2.0, mhigh=2, zhigh=2, nmzmin=0)
    fdata_bytes = make_float_bytes(100.0, 50.0, 30.0, 20.0)
    edata_bytes = make_float_bytes(0.05, 0.10, 0.15, 0.20)

    mock_resn = MagicMock()
    mock_resn.detector = [det]
    mock_resn.tdecay = (86400.0,)  # 1 day in seconds
    mock_resn.read_data.return_value = fdata_bytes
    mock_resn.read_stat.return_value = (None, None, None, None, None, edata_bytes, None)

    rnc_path = tmp_path / "merged_21"
    rnc_path.write_bytes(b"")  # must exist for path.exists() check

    with patch("grid_search.isotope_analysis.Resnuclei", return_value=mock_resn):
        row = read_resnuclei_file(
            path=rnc_path,
            requested_isotopes={1: 3},  # H-3 (tritium): Z=1, A=3
            params={"beame": 0.05},
        )

    assert row is not None
    assert row["H-3 (Bq)"] == pytest.approx(200.0)
    assert row["H-3 (% Error)"] == pytest.approx(5.0)
    assert "d" in row["CoolingTime"]
    assert "beame=0.05" in row["Parameters"]


def test_read_resnuclei_file_isotope_not_present_gives_zero(tmp_path):
    det = Detector(num=1, name="test", volume=1.0, mhigh=2, zhigh=2, nmzmin=0)
    fdata_bytes = make_float_bytes(0.0, 0.0, 0.0, 0.0)
    edata_bytes = make_float_bytes(0.0, 0.0, 0.0, 0.0)

    mock_resn = MagicMock()
    mock_resn.detector = [det]
    mock_resn.tdecay = (0.0,)
    mock_resn.read_data.return_value = fdata_bytes
    mock_resn.read_stat.return_value = (None, None, None, None, None, edata_bytes, None)

    rnc_path = tmp_path / "merged_21"
    rnc_path.write_bytes(b"")

    with patch("grid_search.isotope_analysis.Resnuclei", return_value=mock_resn):
        row = read_resnuclei_file(
            path=rnc_path,
            requested_isotopes={27: 60},  # Co-60 not present in this small detector
            params={},
        )

    assert row is not None
    assert row["Co-60 (Bq)"] == pytest.approx(0.0)
    assert row["Co-60 (% Error)"] == pytest.approx(0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_isotope_analysis.py -v -k "read_resnuclei or missing_rnc"
```

Expected: `AttributeError: module 'grid_search.isotope_analysis' has no attribute 'read_resnuclei_file'`

- [ ] **Step 3: Append `read_resnuclei_file` to `grid_search/isotope_analysis.py`**

Add after the `format_decay_time` function:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_isotope_analysis.py -v -k "read_resnuclei or missing_rnc"
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add grid_search/isotope_analysis.py tests/test_isotope_analysis.py
git commit -m "feat: add read_resnuclei_file isotope extraction"
```

---

## Task 6: Add `run_isotope_analysis` to `grid_search/isotope_analysis.py`

**Files:**
- Modify: `grid_search/isotope_analysis.py`
- Modify: `tests/test_isotope_analysis.py`

This orchestrates the full analysis: iterates combos in state, calls `read_resnuclei_file` for each configured merged file, assembles one DataFrame per combo, and writes a single Excel file.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_isotope_analysis.py`:

```python
import pandas as pd
from grid_search.config import IsotopeConfig
from grid_search.state import StateManager
from grid_search.isotope_analysis import run_isotope_analysis


def test_run_isotope_analysis_writes_excel(tmp_path):
    ia = IsotopeConfig(isotopes={27: 60}, rnc_files=["merged_21"], output="isotopes.xlsx")
    config = MagicMock()
    config.isotope_analysis = ia

    state = StateManager(tmp_path / "state.json")
    state.data = {
        "beame0.05_matGALLIUM": {
            "parameters": {"beame": 0.05, "mat": "GALLIUM"},
            "runs": {},
        }
    }

    fake_row = {
        "CoolingTime": "1.0 d",
        "Parameters": "beame=0.05 mat=GALLIUM",
        "Co-60 (Bq)": 1000.0,
        "Co-60 (% Error)": 5.0,
        "Co-60 (µg)": 0.42,
    }

    with patch("grid_search.isotope_analysis.read_resnuclei_file", return_value=fake_row):
        run_isotope_analysis(tmp_path, config, state)

    output = tmp_path / "isotopes.xlsx"
    assert output.exists()
    df = pd.read_excel(output, sheet_name="beame0.05_matGALLIUM")
    assert "CoolingTime" in df.columns
    assert "Co-60 (Bq)" in df.columns
    assert df["Co-60 (Bq)"].iloc[0] == pytest.approx(1000.0)


def test_run_isotope_analysis_no_files_prints_warning(tmp_path, capsys):
    ia = IsotopeConfig(isotopes={27: 60}, rnc_files=["merged_21"])
    config = MagicMock()
    config.isotope_analysis = ia

    state = StateManager(tmp_path / "state.json")
    state.data = {"beame0.05_matGALLIUM": {"parameters": {}, "runs": {}}}

    with patch("grid_search.isotope_analysis.read_resnuclei_file", return_value=None):
        run_isotope_analysis(tmp_path, config, state)

    assert not (tmp_path / "isotopes.xlsx").exists()
    out = capsys.readouterr().out
    assert "No data found" in out


def test_run_isotope_analysis_combo_filter(tmp_path):
    ia = IsotopeConfig(isotopes={27: 60}, rnc_files=["merged_21"])
    config = MagicMock()
    config.isotope_analysis = ia

    state = StateManager(tmp_path / "state.json")
    state.data = {
        "beame0.05_matGALLIUM": {"parameters": {}, "runs": {}},
        "beame0.1_matGALLIUM": {"parameters": {}, "runs": {}},
    }

    calls = []

    def fake_read(path, isotopes, params):
        calls.append(str(path))
        return None

    with patch("grid_search.isotope_analysis.read_resnuclei_file", side_effect=fake_read):
        run_isotope_analysis(tmp_path, config, state, combo="beame0.05_matGALLIUM")

    assert len(calls) == 1
    assert "beame0.05_matGALLIUM" in calls[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_isotope_analysis.py -v -k "run_isotope"
```

Expected: `AttributeError: module 'grid_search.isotope_analysis' has no attribute 'run_isotope_analysis'`

- [ ] **Step 3: Append `run_isotope_analysis` to `grid_search/isotope_analysis.py`**

Add after `read_resnuclei_file`:

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
```

- [ ] **Step 4: Run all isotope analysis tests**

```bash
pytest tests/test_isotope_analysis.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add grid_search/isotope_analysis.py tests/test_isotope_analysis.py
git commit -m "feat: add run_isotope_analysis Excel output"
```

---

## Task 7: Add `--analyze` flag to `run_grid.py`

**Files:**
- Modify: `run_grid.py`
- Modify: `tests/test_run_grid.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_run_grid.py`:

```python
def test_analyze_flag_no_isotope_config_exits(tmp_path, capsys):
    cfg_path = make_project(tmp_path)
    results = tmp_path / "results"
    results.mkdir()
    (results / "state.json").write_text("{}")

    with pytest.raises(SystemExit):
        run_main([str(cfg_path), "--analyze"])

    out = capsys.readouterr().out
    assert "isotope_analysis" in out


def test_analyze_flag_calls_run_isotope_analysis(tmp_path):
    cfg_path = make_project(tmp_path)
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["isotope_analysis"] = {
        "isotopes": {27: 60},
        "rnc_files": ["merged_21"],
    }
    cfg_path.write_text(yaml.dump(cfg))

    results = tmp_path / "results"
    results.mkdir()
    (results / "state.json").write_text("{}")

    with patch("grid_search.isotope_analysis.run_isotope_analysis") as mock_analyze:
        run_main([str(cfg_path), "--analyze"])

    mock_analyze.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_run_grid.py -v -k "analyze"
```

Expected: `SystemExit` or `error: unrecognized arguments: --analyze`

- [ ] **Step 3: Add `--analyze` to `_parse_args` in `run_grid.py`**

In `_parse_args`, after the `--postprocess` line, add:

```python
p.add_argument("--analyze", action="store_true", help="Run isotope analysis on post-processed data")
```

- [ ] **Step 4: Add exclusivity check and `_do_analyze` in `run_grid.py`**

After the existing `if args.reset and args.postprocess:` block, add:

```python
if args.reset and args.analyze:
    print("Error: --reset and --analyze are mutually exclusive")
    sys.exit(1)
```

Add `_do_analyze` after the existing `_do_postprocess` function:

```python
def _do_analyze(config, state, args):
    if config.isotope_analysis is None:
        print("Error: no isotope_analysis section in config")
        sys.exit(1)
    from grid_search.isotope_analysis import run_isotope_analysis
    run_isotope_analysis(config.output_dir, config, state, combo=args.combo)
```

In `main()`, after the `if args.postprocess:` block, add:

```python
if args.analyze:
    _do_analyze(config, state, args)
    return
```

- [ ] **Step 5: Run the full test suite**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add run_grid.py tests/test_run_grid.py
git commit -m "feat: add --analyze flag for isotope analysis"
```

---

## Spec Coverage Checklist

| Spec requirement | Task |
|---|---|
| `--analyze` flag on `run_grid.py` | 7 |
| `grid_search/resnuclei.py` FORTRAN reader | 2 |
| `IsotopeConfig` dataclass + YAML parsing | 3 |
| `isotope_symbol`, `molar_mass`, `half_life`, `format_decay_time` | 4 |
| `read_resnuclei_file` with extraction algorithm | 5 |
| Missing file skipped silently | 5 |
| `run_isotope_analysis` + Excel output | 6 |
| One sheet per combo, truncated to 31 chars | 6 |
| `--combo` filter | 6 + 7 |
| New Python deps in `pyproject.toml` | 1 |
