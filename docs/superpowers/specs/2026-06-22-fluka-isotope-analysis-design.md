# FlukaIsotopeAnalysis — Design

**Date:** 2026-06-22
**Status:** Approved (design)
**Author:** Antonino Fulci

## Summary

Extract all FLUKA RESNUCLEi reading and isotope-analysis code from
`fluka-grid-search` into a new standalone repository, **FlukaIsotopeAnalysis**.

The new repo provides:

1. A reusable library (pure physics: RESNUCLEi binary reading, isotope/activity
   computation).
2. A standalone CLI, `run_analysis.py <config.yaml>`, that analyses **a single
   FLUKA simulation directory** described by a slim config file.

`fluka-grid-search` then consumes this repo as a git submodule (same pattern
already used for `FlukaQueueSub`) and imports the shared physics primitives,
removing its own copies. This gives a clean, ordered dependency tree and a
single source of truth for the RESNUCLEi/isotope logic.

## Goals

- Run isotope/activation analysis on one simulation folder, driven by a config
  file, independently of the grid-search machinery (no `state.json`, no grid).
- Auto-detect whether RESNUCLEi data is already processed (`.rnc` present, e.g.
  produced by FLAIR) or raw (`fort.21`, etc.) and skip post-processing when not
  needed.
- Keep the physics code in exactly one place, shared between the standalone tool
  and the grid `--analyze` flow.

## Non-Goals

- No grid/parameter sweep, no pivot tables, no multi-combo aggregation in the
  standalone tool (those stay grid-specific in `fluka-grid-search`).
- No plotting (YAGNI for now).
- No change to FLUKA submission or to `FlukaQueueSub`.

## Dependency Direction

```
        fluka-grid-search                 (orchestrator; depends on both)
          │ imports            │ imports
          ▼                    ▼
FlukaIsotopeAnalysis     FlukaQueueSub    (leaf submodules; know nothing
(new submodule)          (existing)        about grid)
```

Hard rule: **the analysis repo must never depend on grid concepts**
(`state.json`, grid parameters, combos). Anything that needs those stays in
`fluka-grid-search`.

## New Repo: FlukaIsotopeAnalysis

### Layout

```
FlukaIsotopeAnalysis/
  pyproject.toml            # name = flukaisotopeanalysis
                            # py-modules = ["run_analysis"]
                            # packages   = ["isotope_analysis"]
  run_analysis.py           # CLI entrypoint: python run_analysis.py analysis.yaml
  isotope_analysis/
    __init__.py
    resnuclei.py            # binary RESNUCLEi reader (moved from grid_search)
    physics.py              # isotope_symbol, molar_mass, half_life, format_decay_time
    reader.py               # read_resnuclei_file (pure primitive)
    config.py               # slim config parser + validation
    excel.py                # single-sim Excel writer
    analysis.py             # orchestration: detect rnc vs raw, post-process, write
  tests/
    test_resnuclei.py
    test_reader.py
    test_physics.py
    test_analysis.py
    fixtures/               # small .rnc fixture(s)
```

### Public import surface (for consumers)

```python
from isotope_analysis.reader import read_resnuclei_file
from isotope_analysis.physics import (
    isotope_symbol, molar_mass, half_life, format_decay_time,
)
from isotope_analysis.resnuclei import Resnuclei, unpack_array
```

Package name `isotope_analysis` is top-level (like `FlukaQueueSub`'s `core` /
`backends`). To avoid ambiguity with the old `grid_search.isotope_analysis`,
the grid module is renamed (see below).

### Dependencies (`pyproject.toml`)

`periodictable`, `radioactivedecay`, `pandas`, `openpyxl`, `pyyaml`.
`requires-python >= 3.10` (match FlukaQueueSub).

### Slim config schema (`analysis.yaml`)

```yaml
analysis:
  directory: /path/to/simulation   # folder with raw fort.21 and/or processed .rnc
  units: [21, 22, 23]              # FLUKA RESNUCLEi unit numbers
  executable: usrsuw               # default; used only to process raw files
  volume: 1000                     # cm³
  isotopes:                        # Z: A
    31: 70
    30: 69
  output: isotopes.xlsx            # written inside `directory`
```

Required: `directory`, `units`, `volume`, `isotopes`. Defaults: `executable:
usrsuw`, `output: isotopes.xlsx`. Validation errors are explicit and exit
non-zero.

### Standalone flow (`analysis.py`)

For each `unit` in `units`:

1. Look for an already-processed file: glob `*{unit}*.rnc` in `directory`.
   - If exactly one match → use it (skip post-processing).
   - If multiple matches → use the first, print a warning listing all.
2. If no `.rnc` match → glob raw files (`*.{unit}` and `fort.{unit}`) in
   `directory`.
   - If found → run `executable` (default `usrsuw`) to merge/convert them into
     `merged_{unit}.rnc` inside `directory`, capturing stdout/stderr to a log;
     then read that file.
   - If none → warn (`unit {unit}: no .rnc and no raw files, skipping`) and
     continue.
3. Read the resolved `.rnc` via `read_resnuclei_file(path, isotopes, params={})`.
   Each file yields one row keyed by its cooling time (`tdecay` read from the
   binary).

After all units: if no rows at all → print a clear message and do **not** write
an empty Excel. Otherwise write the workbook (see below).

### Output (`excel.py`)

A single sheet, `Activity`:

- One row per resolved RESNUCLEi file (i.e. per cooling time / `tdecay`).
- Column `CoolingTime` (human-readable, via `format_decay_time`).
- Per requested isotope: `{sym} (Bq)`, `{sym} (% Error)`, `{sym} (µg)`.

No summary sheet, no pivot (single simulation has no grid parameters). Written
to `directory / output`.

### Post-processing primitive

`analysis.py` runs the configured executable on raw files via `subprocess`,
mirroring the existing `postprocess.run_postprocessing` stdin protocol
(newline-joined input paths, blank line, output name). This is reimplemented in
the analysis repo against a single directory (no combo/run-dir concept), since
`grid_search/postprocess.py` is grid-shaped and stays in grid-search.

### Error handling

- Missing/invalid config field → clear message, exit non-zero.
- `directory` does not exist → exit non-zero.
- Unit with no `.rnc` and no raw files → warn, continue.
- `executable` not on PATH / non-zero exit → error with captured log, exit
  non-zero.
- No data for any unit → message, no Excel written.

### Testing (new repo, TDD)

- `test_resnuclei.py` — binary reader against a small fixture (migrated from
  grid-search).
- `test_physics.py` — isotope symbol/molar mass/half-life/time formatting.
- `test_reader.py` — `read_resnuclei_file` row shape and values on a fixture.
- `test_analysis.py` — detection logic (rnc present → skip postproc; raw only →
  invoke executable, mockable; neither → warn/skip) and Excel output presence.

## Changes in fluka-grid-search

### Submodule + install

```bash
git submodule add https://github.com/AntoninoFulci/FlukaIsotopeAnalysis.git \
    external/FlukaIsotopeAnalysis
```

Installed editable so the top-level `isotope_analysis` package is importable
(same mechanism that makes `FlukaQueueSub`'s `backends`/`core` importable).
README install/setup section updated: submodule init + editable install of the
new submodule. Cluster/example configs unaffected.

### Code moves / refactor

- **Delete** `grid_search/resnuclei.py` (now lives in the submodule).
- **Rename** `grid_search/isotope_analysis.py` → `grid_search/grid_isotope.py`
  to avoid ambiguity with the external top-level `isotope_analysis` package.
- `grid_search/grid_isotope.py` keeps **only** `run_isotope_analysis`
  (the grid-coupled writer: reads `state`, grid parameters, builds per-combo
  sheets + summary + pivot). It **imports** the primitives from the submodule:

  ```python
  from isotope_analysis.reader import read_resnuclei_file
  from isotope_analysis.physics import isotope_symbol
  ```

  Its own copies of `read_resnuclei_file`, `isotope_symbol`, `molar_mass`,
  `half_life`, `format_decay_time`, and the `Resnuclei`/`unpack_array` imports
  are removed.
- Update the import in `run_grid.py`'s `_do_analyze`
  (`from grid_search.grid_isotope import run_isotope_analysis`).

### Tests in fluka-grid-search

- Physics-pure tests (`test_resnuclei.py`, and the isotope-primitive parts of
  `test_isotope_analysis.py`) **migrate** to the new repo.
- What remains in grid-search: a test for the grid writer
  (`run_isotope_analysis`) — per-combo sheets, summary, pivot — exercising the
  state/grid path, with the RESNUCLEi reading satisfied by the submodule (or a
  fixture/mock). Renamed to match `grid_isotope`.
- All existing grid-flow tests must stay green after the refactor.

## Build / Migration Order

1. Create FlukaIsotopeAnalysis repo; move `resnuclei.py` + isotope primitives in;
   split into `physics.py` / `reader.py`; add `pyproject.toml`; migrate physics
   tests (green).
2. Add slim `config.py`, `excel.py`, `analysis.py`, `run_analysis.py`; TDD the
   standalone flow (green).
3. Push repo to GitHub.
4. In fluka-grid-search: add submodule, editable install, delete
   `grid_search/resnuclei.py`, rename to `grid_search/grid_isotope.py`, rewire
   imports to the submodule, update `run_grid.py`.
5. Trim/rename grid tests; run full grid test suite (green).
6. Update README (submodule setup + standalone tool mention).

## Open Risks

- Editable install of two submodules: ensure both `external/FlukaQueueSub` and
  `external/FlukaIsotopeAnalysis` are installed so top-level packages resolve;
  document in README.
- `.rnc` naming from FLAIR may not contain the unit number; the `*{unit}*.rnc`
  glob assumes it does. If a real FLAIR sample shows otherwise, the per-unit
  matching may need an explicit override field later (deferred).
