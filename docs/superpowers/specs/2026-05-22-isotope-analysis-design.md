# Isotope Analysis Module — Design Spec

## Goal

Extend the FLUKA grid search framework with a `--analyze` flag that reads merged RESNUCLEI binary files, extracts user-specified isotopes, computes activity (Bq) and mass (µg), and writes a structured Excel report with one sheet per parameter combination.

## Architecture

### New files

**`grid_search/resnuclei.py`**
Self-contained FORTRAN binary reader, refactored from `docs/references/flair_libs/Data.py` and `fortran.py`. Contains only what is needed to read RESNUCLEI files:
- `fortran_read(f)` and `fortran_skip(f)` — low-level FORTRAN block I/O
- `unpack_array(data)` — unpacks binary float array (`struct.unpack`)
- `Detector` dataclass — fields: `num`, `name`, `volume`, `mhigh`, `zhigh`, `nmzmin`
- `Resnuclei` class — reads header, data, and statistical data from a merged RESNUCLEI file

No dependency on `bmath.py` (only used by `Usrbin`), `Plot.py`, `tool.py`, or `pipe.py`. `log.py`'s `say()` replaced with standard `print`.

**`grid_search/isotope_analysis.py`**
Analysis logic — no file I/O concerns:
- `isotope_symbol(z, a) -> str` — maps (Z, A) to `"Co-60"` style symbol via `periodictable`
- `molar_mass(z, a) -> float` — atomic mass in g/mol via `radioactivedecay`
- `half_life(z, a) -> float` — half-life in seconds via `radioactivedecay`; returns 0 if not found
- `format_decay_time(seconds) -> str` — formats a decay time in seconds to a human-readable string (e.g. `"1 day"`, `"6 months"`)
- `read_resnuclei_file(path, requested_isotopes) -> list[dict]` — reads one merged file, returns one row dict per (Z, A) pair found
- `run_isotope_analysis(output_dir, config, state, combo=None)` — orchestrates: iterates combos (all, or the single combo if `combo` is given), reads files, builds DataFrames, writes Excel

Dependencies: `numpy`, `pandas`, `openpyxl`, `periodictable`, `radioactivedecay`.

### Modified files

**`grid_search/config.py`**
Add `IsotopeConfig` dataclass and optional field on `Config`:

```python
@dataclass
class IsotopeConfig:
    isotopes: dict[int, int]   # Z -> A, e.g. {27: 60, 55: 137}
    rnc_files: list[str]       # filenames in each combo's postproc/, e.g. ["merged_21"]
    output: str = "isotopes.xlsx"
```

`Config.isotope_analysis: Optional[IsotopeConfig] = None`

**`run_grid.py`**
Add `--analyze` flag (mutually exclusive with `--reset`). Add `_do_analyze(config, state, args)` that calls `run_isotope_analysis(config.output_dir, config, state, combo=args.combo)`. If `config.isotope_analysis` is `None`, print a warning and exit.

## Config Schema

```yaml
isotope_analysis:
  isotopes:
    27: 60    # Co-60
    55: 137   # Cs-137
    42: 99    # Mo-99
  rnc_files:
    - merged_21
    - merged_22
    - merged_23
  output: isotopes.xlsx   # optional, default "isotopes.xlsx", saved to output_dir/
```

The `isotope_analysis` section is optional. When absent, `--analyze` exits with a warning.

## Data Flow

```
run_grid.py --analyze [--combo NAME]
    │
    └── _do_analyze(config, state, args)
           │
           for each combo in state (filtered by --combo if given):
           │
           combo_dir = output_dir / combo_name / postproc
           │
           └── for each rnc_file in config.isotope_analysis.rnc_files:
                   │
                   ├── load combo_dir / rnc_file with Resnuclei
                   ├── skip silently if file not found
                   ├── read detector[0]: extract Z, A, Bq, BqErr from the 2D array
                   ├── filter to requested (Z, A) pairs
                   ├── compute mass: µg = (Bq × molar_mass × half_life) / (Nₐ × ln2) × 1e6
                   └── label row with format_decay_time(tdecay[0])  ← read from file
           │
           └── assemble one DataFrame per combo:
                   rows    = one per rnc_file / cooling time
                   columns = CoolingTime, Parameters, then for each isotope:
                             {Symbol} (Bq), {Symbol} (% Error), {Symbol} (µg)
           │
           └── write output_dir / config.isotope_analysis.output
                   one Excel sheet per combo (sheet name = combo name, truncated to 31 chars)
```

## Excel Structure

Sheet name: `beame0.05_matGALLIUM` (truncated to 31 chars if necessary)

| CoolingTime | Parameters | Co-60 (Bq) | Co-60 (% Error) | Co-60 (µg) | Cs-137 (Bq) | … |
|---|---|---|---|---|---|---|
| 1 day | beame=0.05 mat=GALLIUM | 1.2e6 | 2.3 | 0.45 | … | |
| 1 week | beame=0.05 mat=GALLIUM | 8.5e5 | 2.1 | … | | |

- `CoolingTime` is the human-readable decay time derived from `tdecay` in the file
- `Parameters` lists all combo parameters on each row (for Excel filtering / pivot)
- Isotopes with Bq = 0 (not found in detector data) get 0.0 in all columns
- `% Error` is `(BqErr / Bq) * 100`; 0.0 when Bq = 0

## Isotope Data Extraction Logic

The RESNUCLEI detector stores a 2D array indexed by (Z, A). The index mapping (from `docs/references/isotopes.py`):

```python
amax = 2 * zhigh + mhigh + nmzmin
for a in range(1, amax + 1):
    for z in range(zhigh):
        m = a - 2*z - nmzmin - 3
        if m < 0 or m >= mhigh:
            Bq = 0.0
        else:
            pos = z + m * zhigh
            Bq = fdata[pos] * volume
            BqErr = edata[pos] * fdata[pos] * volume  # edata is relative error
```

## Testing

**`tests/test_resnuclei.py`**
- `test_fortran_roundtrip` — write a block with `struct.pack`, read it back with `fortran_read`, verify bytes match
- `test_fortran_skip` — write two blocks, skip first, read second, verify
- No real FLUKA files required

**`tests/test_isotope_analysis.py`**
- `test_read_resnuclei_file_returns_known_isotope` — mock `Resnuclei` to return controlled arrays; verify Bq, % Error, µg columns are correct
- `test_run_isotope_analysis_writes_excel` — mock `Resnuclei`, run full analysis on `tmp_path`, verify `isotopes.xlsx` exists with correct sheet names and column headers
- `test_missing_rnc_file_is_skipped` — if a configured `rnc_file` does not exist, no exception is raised

**`tests/test_config.py`**
- Extend to cover `isotope_analysis` section: verify `IsotopeConfig` is parsed correctly and that `Config.isotope_analysis` is `None` when section is absent

## Dependencies

New Python packages required (add to `requirements.txt` or `pyproject.toml`):
- `pandas`
- `openpyxl`
- `periodictable`
- `radioactivedecay`
- `numpy` (likely already present)
