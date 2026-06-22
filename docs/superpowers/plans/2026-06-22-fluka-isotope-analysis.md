# FlukaIsotopeAnalysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract FLUKA RESNUCLEi/isotope physics into a new standalone repo `FlukaIsotopeAnalysis` with a config-driven single-simulation CLI, then make `fluka-grid-search` consume it as a git submodule (removing its duplicate copies).

**Architecture:** Phase A builds the new repo at `/Users/tonyf/Work/FlukaIsotopeAnalysis` (top-level package `isotope_analysis`: `resnuclei`, `physics`, `reader`, `config`, `excel`, `analysis` + `run_analysis.py` CLI), TDD, then pushes to GitHub. Phase B adds it as a submodule under `external/`, deletes `grid_search/resnuclei.py`, renames `grid_search/isotope_analysis.py` → `grid_search/grid_isotope.py` importing the submodule primitives, and migrates the physics tests out.

**Tech Stack:** Python ≥3.10, pandas, openpyxl, periodictable, radioactivedecay, pyyaml, pytest.

**Reference spec:** `docs/superpowers/specs/2026-06-22-fluka-isotope-analysis-design.md`

---

## File Structure

New repo `/Users/tonyf/Work/FlukaIsotopeAnalysis`:
- `pyproject.toml` — package metadata + deps
- `run_analysis.py` — CLI entrypoint
- `isotope_analysis/__init__.py`
- `isotope_analysis/resnuclei.py` — binary reader (verbatim move)
- `isotope_analysis/physics.py` — `isotope_symbol`, `molar_mass`, `half_life`, `format_decay_time`
- `isotope_analysis/reader.py` — `read_resnuclei_file`
- `isotope_analysis/config.py` — `AnalysisConfig` + `load_analysis_config`
- `isotope_analysis/excel.py` — `write_activity_workbook`
- `isotope_analysis/analysis.py` — `resolve_rnc`, `run_analysis`
- `tests/test_resnuclei.py`, `tests/test_physics.py`, `tests/test_reader.py`, `tests/test_config.py`, `tests/test_excel.py`, `tests/test_analysis.py`, `tests/test_cli.py`

Modified in `fluka-grid-search`:
- delete `grid_search/resnuclei.py`
- rename `grid_search/isotope_analysis.py` → `grid_search/grid_isotope.py` (keep only grid writer, import primitives)
- `run_grid.py` (`_do_analyze` import)
- `tests/test_isotope_analysis.py` → `tests/test_grid_isotope.py` (trim physics tests, fix patch targets)
- delete `tests/test_resnuclei.py` (migrated)
- `.gitmodules`, `README.md`

---

# PHASE A — New repo: FlukaIsotopeAnalysis

> All Phase A commands run with CWD `/Users/tonyf/Work/FlukaIsotopeAnalysis` unless stated. `$R` below = `/Users/tonyf/Work/FlukaIsotopeAnalysis`.

## Task A1: Scaffold repo

**Files:**
- Create: `$R/pyproject.toml`
- Create: `$R/isotope_analysis/__init__.py`
- Create: `$R/.gitignore`

- [ ] **Step 1: Create directories and init git**

```bash
mkdir -p /Users/tonyf/Work/FlukaIsotopeAnalysis/isotope_analysis
mkdir -p /Users/tonyf/Work/FlukaIsotopeAnalysis/tests
cd /Users/tonyf/Work/FlukaIsotopeAnalysis && git init -q && echo ok
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "flukaisotopeanalysis"
version = "0.1.0"
description = "Standalone FLUKA RESNUCLEi isotope/activation analysis"
requires-python = ">=3.10"
dependencies = [
    "pyyaml",
    "pandas",
    "openpyxl",
    "periodictable",
    "radioactivedecay",
]

[project.optional-dependencies]
dev = ["pytest"]

[tool.setuptools]
py-modules = ["run_analysis"]
packages = ["isotope_analysis"]
```

- [ ] **Step 3: Write `isotope_analysis/__init__.py`**

```python
"""Standalone FLUKA RESNUCLEi isotope/activation analysis."""
```

- [ ] **Step 4: Write `.gitignore`**

```
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
*.xlsx
```

- [ ] **Step 5: Install editable**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pip install -e ".[dev]"`
Expected: `Successfully installed flukaisotopeanalysis-0.1.0`

- [ ] **Step 6: Commit**

```bash
cd /Users/tonyf/Work/FlukaIsotopeAnalysis
git add -A && git commit -q -m "chore: scaffold FlukaIsotopeAnalysis package"
```

---

## Task A2: resnuclei.py (binary reader)

**Files:**
- Create: `$R/isotope_analysis/resnuclei.py`
- Test: `$R/tests/test_resnuclei.py`

- [ ] **Step 1: Write the test**

```python
import io
import struct
import pytest
from isotope_analysis.resnuclei import fortran_read, fortran_skip, unpack_array, Detector


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

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_resnuclei.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'isotope_analysis.resnuclei'`

- [ ] **Step 3: Write `isotope_analysis/resnuclei.py`**

Copy the full content of `fluka-grid-search/grid_search/resnuclei.py` verbatim (it has no internal relative imports). The complete file:

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
        self.tdecay: float = 0.0
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
        try:
            self._read_base_header()
            if self.ncase <= 0:
                self.evol = True
                self.ncase = -self.ncase
                data = fortran_read(self._f)
                if data is None:
                    raise IOError("Unexpected EOF reading evolution header")
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
                        if data is None:
                            raise IOError("Unexpected EOF reading ISOMERS header")
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
                    self.tdecay = struct.unpack("=f", data)[0]
                else:
                    self.tdecay = 0.0

                size = det.zhigh * det.mhigh * 4
                if size != fortran_skip(self._f):
                    raise IOError("Invalid RESNUCLEi file")
        finally:
            self._close()

    def read_data(self, n: int) -> Optional[bytes]:
        self._open()
        try:
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
            return data
        finally:
            self._close()

    def read_stat(self, n: int) -> Optional[tuple]:
        if self.statpos < 0:
            return None
        self._open()
        try:
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
            return (total, A, errA, Z, errZ, data, iso)
        finally:
            self._close()
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_resnuclei.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
cd /Users/tonyf/Work/FlukaIsotopeAnalysis
git add -A && git commit -q -m "feat: RESNUCLEi binary reader"
```

---

## Task A3: physics.py (isotope helpers)

**Files:**
- Create: `$R/isotope_analysis/physics.py`
- Test: `$R/tests/test_physics.py`

- [ ] **Step 1: Write the test**

```python
import pytest
from isotope_analysis.physics import (
    isotope_symbol, molar_mass, half_life, format_decay_time,
)


def test_isotope_symbol_co60():
    assert isotope_symbol(27, 60) == "Co-60"


def test_isotope_symbol_cs137():
    assert isotope_symbol(55, 137) == "Cs-137"


def test_molar_mass_co60_positive():
    assert molar_mass(27, 60) > 50.0


def test_molar_mass_unknown_returns_zero():
    assert molar_mass(999, 999) == 0.0


def test_half_life_co60_positive():
    assert half_life(27, 60) > 0.0


def test_half_life_unknown_returns_zero():
    assert half_life(999, 999) == 0.0


def test_half_life_stable_isotope_returns_zero():
    assert half_life(26, 56) == 0.0


def test_format_decay_time_seconds():
    assert format_decay_time(30) == "30 s"


def test_format_decay_time_minutes():
    assert format_decay_time(120) == "2 min"


def test_format_decay_time_hours():
    assert format_decay_time(7200) == "2 h"


def test_format_decay_time_days():
    assert format_decay_time(3 * 86400) == "3.0 d"


def test_format_decay_time_zero():
    assert format_decay_time(0) == "0 s"
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_physics.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'isotope_analysis.physics'`

- [ ] **Step 3: Write `isotope_analysis/physics.py`**

```python
from __future__ import annotations
import math

import periodictable
import radioactivedecay as rd


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
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_physics.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
cd /Users/tonyf/Work/FlukaIsotopeAnalysis
git add -A && git commit -q -m "feat: isotope physics helpers"
```

---

## Task A4: reader.py (read_resnuclei_file)

**Files:**
- Create: `$R/isotope_analysis/reader.py`
- Test: `$R/tests/test_reader.py`

- [ ] **Step 1: Write the test**

```python
import struct
import pytest
from unittest.mock import patch, MagicMock
from isotope_analysis.reader import read_resnuclei_file
from isotope_analysis.resnuclei import Detector


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
    det = Detector(num=1, name="test", volume=2.0, mhigh=2, zhigh=2, nmzmin=0)
    fdata_bytes = make_float_bytes(100.0, 50.0, 30.0, 20.0)
    edata_bytes = make_float_bytes(0.05, 0.10, 0.15, 0.20)

    mock_resn = MagicMock()
    mock_resn.detector = [det]
    mock_resn.tdecay = 86400.0
    mock_resn.read_data.return_value = fdata_bytes
    mock_resn.read_stat.return_value = (None, None, None, None, None, edata_bytes, None)

    rnc_path = tmp_path / "merged_21.rnc"
    rnc_path.write_bytes(b"")

    with patch("isotope_analysis.reader.Resnuclei", return_value=mock_resn):
        row = read_resnuclei_file(
            path=rnc_path,
            requested_isotopes={1: 3},
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
    mock_resn.tdecay = 0.0
    mock_resn.read_data.return_value = fdata_bytes
    mock_resn.read_stat.return_value = (None, None, None, None, None, edata_bytes, None)

    rnc_path = tmp_path / "merged_21.rnc"
    rnc_path.write_bytes(b"")

    with patch("isotope_analysis.reader.Resnuclei", return_value=mock_resn):
        row = read_resnuclei_file(
            path=rnc_path,
            requested_isotopes={27: 60},
            params={},
        )

    assert row is not None
    assert row["Co-60 (Bq)"] == pytest.approx(0.0)
    assert row["Co-60 (% Error)"] == pytest.approx(0.0)
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_reader.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'isotope_analysis.reader'`

- [ ] **Step 3: Write `isotope_analysis/reader.py`**

```python
from __future__ import annotations
import math
from pathlib import Path
from typing import Optional

from .resnuclei import Resnuclei, unpack_array
from .physics import isotope_symbol, molar_mass, half_life, format_decay_time

_AVOGADRO = 6.02214076e23


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
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_reader.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /Users/tonyf/Work/FlukaIsotopeAnalysis
git add -A && git commit -q -m "feat: read_resnuclei_file primitive"
```

---

## Task A5: config.py (slim analysis config)

**Files:**
- Create: `$R/isotope_analysis/config.py`
- Test: `$R/tests/test_config.py`

- [ ] **Step 1: Write the test**

```python
import pytest
from pathlib import Path
from isotope_analysis.config import load_analysis_config, AnalysisConfig


def _write_config(tmp_path, body: str) -> Path:
    p = tmp_path / "analysis.yaml"
    p.write_text(body)
    return p


def test_load_full_config(tmp_path):
    sim = tmp_path / "sim"
    sim.mkdir()
    cfg = _write_config(tmp_path, f"""
analysis:
  directory: {sim}
  units: [21, 22]
  executable: usrsuw
  volume: 1000
  isotopes:
    31: 70
    30: 69
  output: out.xlsx
""")
    c = load_analysis_config(cfg)
    assert isinstance(c, AnalysisConfig)
    assert c.directory == sim
    assert c.units == [21, 22]
    assert c.executable == "usrsuw"
    assert c.volume == 1000.0
    assert c.isotopes == {31: 70, 30: 69}
    assert c.output == "out.xlsx"


def test_defaults_applied(tmp_path):
    sim = tmp_path / "sim"
    sim.mkdir()
    cfg = _write_config(tmp_path, f"""
analysis:
  directory: {sim}
  units: [21]
  volume: 500
  isotopes:
    27: 60
""")
    c = load_analysis_config(cfg)
    assert c.executable == "usrsuw"
    assert c.output == "isotopes.xlsx"


def test_missing_directory_field_raises(tmp_path):
    cfg = _write_config(tmp_path, """
analysis:
  units: [21]
  volume: 1
  isotopes:
    27: 60
""")
    with pytest.raises(ValueError, match="directory"):
        load_analysis_config(cfg)


def test_nonexistent_directory_raises(tmp_path):
    cfg = _write_config(tmp_path, f"""
analysis:
  directory: {tmp_path / 'does_not_exist'}
  units: [21]
  volume: 1
  isotopes:
    27: 60
""")
    with pytest.raises(ValueError, match="does not exist"):
        load_analysis_config(cfg)


def test_empty_units_raises(tmp_path):
    sim = tmp_path / "sim"
    sim.mkdir()
    cfg = _write_config(tmp_path, f"""
analysis:
  directory: {sim}
  units: []
  volume: 1
  isotopes:
    27: 60
""")
    with pytest.raises(ValueError, match="units"):
        load_analysis_config(cfg)
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'isotope_analysis.config'`

- [ ] **Step 3: Write `isotope_analysis/config.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class AnalysisConfig:
    directory: Path
    units: list[int]
    isotopes: dict[int, int]
    volume: float
    executable: str = "usrsuw"
    output: str = "isotopes.xlsx"


def load_analysis_config(path: Path) -> AnalysisConfig:
    raw = yaml.safe_load(Path(path).read_text())
    if not raw or "analysis" not in raw:
        raise ValueError("config must contain a top-level 'analysis' section")
    a = raw["analysis"]

    for field in ("directory", "units", "volume", "isotopes"):
        if field not in a:
            raise ValueError(f"analysis.{field} is required")

    directory = Path(a["directory"])
    if not directory.exists():
        raise ValueError(f"analysis.directory does not exist: {directory}")

    units = [int(u) for u in a["units"]]
    if not units:
        raise ValueError("analysis.units must list at least one unit number")

    isotopes = {int(k): int(v) for k, v in a["isotopes"].items()}
    if not isotopes:
        raise ValueError("analysis.isotopes must list at least one Z: A pair")

    return AnalysisConfig(
        directory=directory,
        units=units,
        isotopes=isotopes,
        volume=float(a["volume"]),
        executable=a.get("executable", "usrsuw"),
        output=a.get("output", "isotopes.xlsx"),
    )
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_config.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
cd /Users/tonyf/Work/FlukaIsotopeAnalysis
git add -A && git commit -q -m "feat: slim analysis config loader"
```

---

## Task A6: excel.py (single-sim workbook)

**Files:**
- Create: `$R/isotope_analysis/excel.py`
- Test: `$R/tests/test_excel.py`

> Note (refinement over spec): the `Activity` sheet adds a `(Bq/cm³)` column per
> isotope = `(Bq) / volume`, so the config `volume` field is meaningful in the
> single-sim output. Columns per isotope: `(Bq)`, `(Bq/cm³)`, `(% Error)`, `(µg)`.

- [ ] **Step 1: Write the test**

```python
import pytest
import pandas as pd
from isotope_analysis.excel import write_activity_workbook


def test_write_activity_workbook(tmp_path):
    rows = [
        {
            "_tdecay_s": 86400.0, "CoolingTime": "1.0 d", "Parameters": "",
            "Co-60 (Bq)": 1000.0, "Co-60 (% Error)": 5.0, "Co-60 (µg)": 0.42,
        },
        {
            "_tdecay_s": 0.0, "CoolingTime": "0 s", "Parameters": "",
            "Co-60 (Bq)": 2000.0, "Co-60 (% Error)": 4.0, "Co-60 (µg)": 0.84,
        },
    ]
    out = tmp_path / "out.xlsx"
    write_activity_workbook(rows, isotopes={27: 60}, volume=1000.0, output_path=out)

    assert out.exists()
    df = pd.read_excel(out, sheet_name="Activity")
    # sorted by _tdecay_s ascending => first row is "0 s"
    assert df["CoolingTime"].iloc[0] == "0 s"
    assert df["Co-60 (Bq)"].iloc[0] == pytest.approx(2000.0)
    assert df["Co-60 (Bq/cm³)"].iloc[0] == pytest.approx(2.0)
    assert "Co-60 (% Error)" in df.columns
    assert "Co-60 (µg)" in df.columns
    # internal sort key must not leak into the sheet
    assert "_tdecay_s" not in df.columns
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_excel.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'isotope_analysis.excel'`

- [ ] **Step 3: Write `isotope_analysis/excel.py`**

```python
from __future__ import annotations
from pathlib import Path

import pandas as pd

from .physics import isotope_symbol


def write_activity_workbook(
    rows: list[dict],
    isotopes: dict[int, int],
    volume: float,
    output_path: Path,
) -> None:
    rows_sorted = sorted(rows, key=lambda r: r["_tdecay_s"])
    syms = [isotope_symbol(z, a) for z, a in sorted(isotopes.items())]

    records: list[dict] = []
    for r in rows_sorted:
        rec: dict = {"CoolingTime": r["CoolingTime"]}
        for sym in syms:
            bq = r.get(f"{sym} (Bq)", 0.0)
            rec[f"{sym} (Bq)"] = bq
            rec[f"{sym} (Bq/cm³)"] = bq / volume if volume else 0.0
            rec[f"{sym} (% Error)"] = r.get(f"{sym} (% Error)", 0.0)
            rec[f"{sym} (µg)"] = r.get(f"{sym} (µg)", 0.0)
        records.append(rec)

    df = pd.DataFrame(records)
    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Activity", index=False)
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_excel.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
cd /Users/tonyf/Work/FlukaIsotopeAnalysis
git add -A && git commit -q -m "feat: single-sim Activity workbook writer"
```

---

## Task A7: analysis.py (orchestration)

**Files:**
- Create: `$R/isotope_analysis/analysis.py`
- Test: `$R/tests/test_analysis.py`

- [ ] **Step 1: Write the test**

```python
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from isotope_analysis.config import AnalysisConfig
from isotope_analysis import analysis as A


def _cfg(directory, **kw):
    return AnalysisConfig(
        directory=directory,
        units=kw.get("units", [21]),
        isotopes=kw.get("isotopes", {27: 60}),
        volume=kw.get("volume", 1000.0),
        executable=kw.get("executable", "usrsuw"),
        output=kw.get("output", "isotopes.xlsx"),
    )


def test_resolve_rnc_uses_existing_rnc(tmp_path):
    (tmp_path / "merged_21.rnc").write_bytes(b"")
    with patch.object(A.subprocess, "run") as mock_run:
        result = A.resolve_rnc(tmp_path, 21, "usrsuw")
    assert result == tmp_path / "merged_21.rnc"
    mock_run.assert_not_called()  # already processed -> no postproc


def test_resolve_rnc_processes_raw_when_no_rnc(tmp_path):
    (tmp_path / "sim001_fort.21").write_bytes(b"")

    def fake_run(*args, **kwargs):
        (tmp_path / "merged_21.rnc").write_bytes(b"")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(A.subprocess, "run", side_effect=fake_run) as mock_run:
        result = A.resolve_rnc(tmp_path, 21, "usrsuw")
    assert result == tmp_path / "merged_21.rnc"
    mock_run.assert_called_once()


def test_resolve_rnc_returns_none_when_no_data(tmp_path):
    with patch.object(A.subprocess, "run") as mock_run:
        result = A.resolve_rnc(tmp_path, 99, "usrsuw")
    assert result is None
    mock_run.assert_not_called()


def test_run_analysis_writes_workbook(tmp_path):
    (tmp_path / "merged_21.rnc").write_bytes(b"")
    cfg = _cfg(tmp_path, units=[21])
    fake_row = {
        "_tdecay_s": 0.0, "CoolingTime": "0 s", "Parameters": "",
        "Co-60 (Bq)": 1000.0, "Co-60 (% Error)": 5.0, "Co-60 (µg)": 0.42,
    }
    with patch.object(A, "read_resnuclei_file", return_value=fake_row):
        A.run_analysis(cfg)
    assert (tmp_path / "isotopes.xlsx").exists()


def test_run_analysis_no_data_writes_nothing(tmp_path, capsys):
    cfg = _cfg(tmp_path, units=[99])
    A.run_analysis(cfg)
    assert not (tmp_path / "isotopes.xlsx").exists()
    assert "no data" in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_analysis.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'isotope_analysis.analysis'`

- [ ] **Step 3: Write `isotope_analysis/analysis.py`**

```python
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Optional

from .config import AnalysisConfig
from .reader import read_resnuclei_file
from .excel import write_activity_workbook


def resolve_rnc(directory: Path, unit: int, executable: str) -> Optional[Path]:
    """Return the .rnc file for `unit`, post-processing raw files if needed."""
    existing = sorted(directory.glob(f"*{unit}*.rnc"))
    if existing:
        if len(existing) > 1:
            names = ", ".join(p.name for p in existing)
            print(f"[warn] unit {unit}: multiple .rnc match ({names}); using {existing[0].name}")
        return existing[0]

    raw = sorted({*directory.glob(f"*.{unit}"), *directory.glob(f"fort.{unit}")})
    if not raw:
        return None

    output_name = f"merged_{unit}.rnc"
    stdin_input = "\n".join(str(f) for f in raw) + "\n\n" + output_name + "\n"
    result = subprocess.run(
        [executable],
        input=stdin_input,
        text=True,
        capture_output=True,
        cwd=directory,
    )
    (directory / f"{Path(executable).name}_{unit}.log").write_text(
        result.stdout + result.stderr
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{executable} failed for unit {unit} (exit {result.returncode}); "
            f"see {executable}_{unit}.log"
        )

    out_path = directory / output_name
    if not out_path.exists():
        raise RuntimeError(
            f"{executable} did not produce {output_name} for unit {unit}; "
            f"see {executable}_{unit}.log"
        )
    return out_path


def run_analysis(config: AnalysisConfig) -> None:
    directory = config.directory
    rows: list[dict] = []
    for unit in config.units:
        path = resolve_rnc(directory, unit, config.executable)
        if path is None:
            print(f"[warn] unit {unit}: no .rnc and no raw files, skipping")
            continue
        row = read_resnuclei_file(path, config.isotopes, {})
        if row is None:
            print(f"[warn] unit {unit}: {path.name} has no detector data, skipping")
            continue
        rows.append(row)

    if not rows:
        print("[analyze] no data found for any unit; nothing written")
        return

    output_path = directory / config.output
    write_activity_workbook(rows, config.isotopes, config.volume, output_path)
    print(f"[analyze] written {output_path}")
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_analysis.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
cd /Users/tonyf/Work/FlukaIsotopeAnalysis
git add -A && git commit -q -m "feat: analysis orchestration (resolve + run)"
```

---

## Task A8: run_analysis.py (CLI)

**Files:**
- Create: `$R/run_analysis.py`
- Test: `$R/tests/test_cli.py`

- [ ] **Step 1: Write the test**

```python
import sys
import pytest
from unittest.mock import patch
import run_analysis


def test_main_loads_config_and_runs(tmp_path):
    sim = tmp_path / "sim"
    sim.mkdir()
    cfg = tmp_path / "analysis.yaml"
    cfg.write_text(f"""
analysis:
  directory: {sim}
  units: [21]
  volume: 1000
  isotopes:
    27: 60
""")
    with patch.object(run_analysis, "run_analysis") as mock_run:
        with patch.object(sys, "argv", ["run_analysis.py", str(cfg)]):
            run_analysis.main()
    mock_run.assert_called_once()
    passed_cfg = mock_run.call_args.args[0]
    assert passed_cfg.directory == sim
    assert passed_cfg.units == [21]


def test_main_requires_config_arg():
    with patch.object(sys, "argv", ["run_analysis.py"]):
        with pytest.raises(SystemExit):
            run_analysis.main()
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'run_analysis'`

- [ ] **Step 3: Write `run_analysis.py`**

```python
#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path

from isotope_analysis.config import load_analysis_config
from isotope_analysis.analysis import run_analysis


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse a single FLUKA simulation directory (RESNUCLEi isotopes)."
    )
    parser.add_argument("config", type=Path, help="path to analysis.yaml")
    args = parser.parse_args()

    config = load_analysis_config(args.config)
    run_analysis(config)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest tests/test_cli.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Run full suite + commit**

Run: `cd /Users/tonyf/Work/FlukaIsotopeAnalysis && pytest -q`
Expected: PASS (all tests)

```bash
cd /Users/tonyf/Work/FlukaIsotopeAnalysis
git add -A && git commit -q -m "feat: run_analysis CLI entrypoint"
```

---

## Task A9: README + push to GitHub

**Files:**
- Create: `$R/README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# FlukaIsotopeAnalysis

Standalone isotope/activation analysis for FLUKA `RESNUCLEi` output.

Reads raw `RESNUCLEi` binaries (`fort.21`, …) and/or already-processed `.rnc`
files (e.g. from FLAIR), computes per-isotope activity (Bq), error, and mass
(µg), and writes an Excel workbook — for a single simulation directory.

## Install

```bash
pip install -e .
```

## Usage

```bash
python run_analysis.py analysis.yaml
```

`analysis.yaml`:

```yaml
analysis:
  directory: /path/to/simulation
  units: [21, 22, 23]
  executable: usrsuw       # optional, default usrsuw
  volume: 1000             # cm³
  isotopes:                # Z: A
    31: 70
    30: 69
  output: isotopes.xlsx    # optional
```

For each unit: an existing `*<unit>*.rnc` is used as-is; otherwise raw
`*.<unit>`/`fort.<unit>` files are processed with `executable` into
`merged_<unit>.rnc`. Output: an `Activity` sheet, one row per cooling time.

## Library use

```python
from isotope_analysis.reader import read_resnuclei_file
from isotope_analysis.physics import isotope_symbol, half_life
```
````

- [ ] **Step 2: Commit**

```bash
cd /Users/tonyf/Work/FlukaIsotopeAnalysis
git add -A && git commit -q -m "docs: README"
```

- [ ] **Step 3: Create GitHub repo and push**

Run:
```bash
cd /Users/tonyf/Work/FlukaIsotopeAnalysis
gh repo create AntoninoFulci/FlukaIsotopeAnalysis --public --source=. --remote=origin --push
```
Expected: repo created, `main` pushed. Confirm with `git remote -v`.

---

# PHASE B — Integrate into fluka-grid-search

> All Phase B commands run with CWD `/Users/tonyf/Work/fluka-grid-search`.

## Task B1: Add submodule + editable install

**Files:**
- Modify: `.gitmodules`
- Create: `external/FlukaIsotopeAnalysis` (submodule)

- [ ] **Step 1: Add submodule**

Run:
```bash
cd /Users/tonyf/Work/fluka-grid-search
git submodule add https://github.com/AntoninoFulci/FlukaIsotopeAnalysis.git external/FlukaIsotopeAnalysis
```
Expected: cloned into `external/FlukaIsotopeAnalysis`; `.gitmodules` gains a second entry.

- [ ] **Step 2: Editable install of the submodule**

Run: `pip install -e /Users/tonyf/Work/fluka-grid-search/external/FlukaIsotopeAnalysis`
Expected: `Successfully installed flukaisotopeanalysis-0.1.0`

- [ ] **Step 3: Verify import resolves**

Run: `cd /Users/tonyf/Work/fluka-grid-search && python -c "from isotope_analysis.reader import read_resnuclei_file; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
cd /Users/tonyf/Work/fluka-grid-search
git add .gitmodules external/FlukaIsotopeAnalysis
git commit -q -m "feat: add FlukaIsotopeAnalysis submodule"
```

---

## Task B2: Replace grid_search physics with submodule imports

**Files:**
- Delete: `grid_search/resnuclei.py`
- Rename: `grid_search/isotope_analysis.py` → `grid_search/grid_isotope.py`
- Modify: the renamed file (imports + remove moved primitives)

- [ ] **Step 1: Delete the moved reader and rename the module**

Run:
```bash
cd /Users/tonyf/Work/fluka-grid-search
git rm -q grid_search/resnuclei.py
git mv grid_search/isotope_analysis.py grid_search/grid_isotope.py
```

- [ ] **Step 2: Rewrite the head of `grid_search/grid_isotope.py`**

Replace the top of the file (the old imports + the moved helper functions
`isotope_symbol`, `molar_mass`, `half_life`, `format_decay_time`,
`read_resnuclei_file`, and the `_AVOGADRO` constant — original lines 1–117)
with imports from the submodule. The new file head:

```python
from __future__ import annotations
from pathlib import Path
from typing import Optional

import pandas as pd

from isotope_analysis.reader import read_resnuclei_file
from isotope_analysis.physics import isotope_symbol
```

Keep everything from `def _build_summary_sheet(` onward **unchanged**
(`_build_summary_sheet`, `_build_pivot_sheet`, `run_isotope_analysis`). Those
functions already call `read_resnuclei_file` and `isotope_symbol`, which are now
imported from the submodule.

- [ ] **Step 3: Verify the module imports cleanly**

Run: `cd /Users/tonyf/Work/fluka-grid-search && python -c "from grid_search.grid_isotope import run_isotope_analysis; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
cd /Users/tonyf/Work/fluka-grid-search
git add -A
git commit -q -m "refactor: grid_isotope imports physics from FlukaIsotopeAnalysis submodule"
```

---

## Task B3: Update run_grid.py import

**Files:**
- Modify: `run_grid.py` (`_do_analyze`)

- [ ] **Step 1: Update the import in `_do_analyze`**

In `run_grid.py`, change the line inside `_do_analyze`:

```python
    from grid_search.isotope_analysis import run_isotope_analysis
```

to:

```python
    from grid_search.grid_isotope import run_isotope_analysis
```

- [ ] **Step 2: Verify the entrypoint imports**

Run: `cd /Users/tonyf/Work/fluka-grid-search && python -c "import run_grid; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/tonyf/Work/fluka-grid-search
git add run_grid.py
git commit -q -m "refactor: point run_grid --analyze at grid_isotope"
```

---

## Task B4: Migrate / trim grid tests

**Files:**
- Delete: `tests/test_resnuclei.py` (physics reader now tested in the submodule)
- Rename: `tests/test_isotope_analysis.py` → `tests/test_grid_isotope.py`
- Modify: the renamed test (drop migrated physics/reader tests, fix patch targets & imports)

- [ ] **Step 1: Delete the migrated reader test and rename the grid test**

Run:
```bash
cd /Users/tonyf/Work/fluka-grid-search
git rm -q tests/test_resnuclei.py
git mv tests/test_isotope_analysis.py tests/test_grid_isotope.py
```

- [ ] **Step 2: Edit `tests/test_grid_isotope.py`**

Make these exact changes:

1. Replace the top import block:

```python
from grid_search.isotope_analysis import (
    isotope_symbol,
    molar_mass,
    half_life,
    format_decay_time,
    _build_pivot_sheet,
)
from openpyxl import load_workbook
from grid_search.config import IsotopeConfig
from grid_search.isotope_analysis import run_isotope_analysis
```

with:

```python
from grid_search.grid_isotope import _build_pivot_sheet, run_isotope_analysis
from openpyxl import load_workbook
from grid_search.config import IsotopeConfig
```

2. Delete these now-migrated tests entirely (they live in the new repo's
   `test_physics.py` / `test_reader.py`): `test_isotope_symbol_co60`,
   `test_isotope_symbol_cs137`, `test_molar_mass_co60_positive`,
   `test_molar_mass_unknown_returns_zero`, `test_half_life_co60_positive`,
   `test_half_life_unknown_returns_zero`, `test_half_life_stable_isotope_returns_zero`,
   `test_format_decay_time_seconds`, `test_format_decay_time_minutes`,
   `test_format_decay_time_hours`, `test_format_decay_time_days`,
   `test_format_decay_time_zero`, `test_missing_rnc_file_is_skipped`,
   `test_read_resnuclei_file_returns_known_isotope`,
   `test_read_resnuclei_file_isotope_not_present_gives_zero`.

3. Delete the now-unused mid-file import/helper block:

```python
import struct
from unittest.mock import patch, MagicMock
from grid_search.isotope_analysis import read_resnuclei_file
from grid_search.resnuclei import Detector
from grid_search.state import StateManager


def make_float_bytes(*values):
    return struct.pack(f"={len(values)}f", *values)
```

and replace it with only what the remaining grid-writer tests need:

```python
from unittest.mock import patch, MagicMock
from grid_search.state import StateManager
```

4. Fix the patch target in **every** remaining test: replace each
   `patch("grid_search.isotope_analysis.read_resnuclei_file", ...)` with
   `patch("grid_search.grid_isotope.read_resnuclei_file", ...)`.

- [ ] **Step 3: Run the renamed test file, verify green**

Run: `cd /Users/tonyf/Work/fluka-grid-search && pytest tests/test_grid_isotope.py -q`
Expected: PASS (the run_isotope_analysis / summary / pivot tests; ~17 passed)

- [ ] **Step 4: Commit**

```bash
cd /Users/tonyf/Work/fluka-grid-search
git add -A
git commit -q -m "test: migrate physics tests out, retarget grid_isotope tests"
```

---

## Task B5: Full suite + README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the full grid-search test suite**

Run: `cd /Users/tonyf/Work/fluka-grid-search && pytest -q`
Expected: PASS (all). If any test still references `grid_search.isotope_analysis`
or `grid_search.resnuclei`, fix the import/patch target to `grid_search.grid_isotope`.

- [ ] **Step 2: Update README install section**

In `README.md`, in the install section, after the existing submodule note for
FlukaQueueSub, document both submodules and the standalone tool:

````markdown
This project uses two git submodules under `external/`:

- `FlukaQueueSub` — multi-backend job submission
- `FlukaIsotopeAnalysis` — RESNUCLEi isotope/activation analysis

Clone with submodules and install them editable:

```bash
git clone --recurse-submodules <repo-url>
cd fluka-grid-search
pip install -e .
pip install -e external/FlukaQueueSub
pip install -e external/FlukaIsotopeAnalysis
```

For a standalone single-simulation analysis (no grid), use the tool directly:

```bash
python external/FlukaIsotopeAnalysis/run_analysis.py analysis.yaml
```
````

- [ ] **Step 3: Commit**

```bash
cd /Users/tonyf/Work/fluka-grid-search
git add README.md
git commit -q -m "docs: document FlukaIsotopeAnalysis submodule + standalone analysis"
```

---

## Done

- New repo `FlukaIsotopeAnalysis` owns all RESNUCLEi/isotope physics + the
  standalone single-sim CLI, fully tested.
- `fluka-grid-search` consumes it as a submodule; `grid_search` has no duplicate
  physics code; the grid `--analyze` flow uses the shared primitives.
- Dependency direction: `fluka-grid-search` → {`FlukaIsotopeAnalysis`,
  `FlukaQueueSub`}; neither submodule depends on grid concepts.
