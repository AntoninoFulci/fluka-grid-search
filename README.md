# fluka-grid-search

A Python tool for running FLUKA Monte Carlo simulations over a parameter grid, built on top of [task-spooler](https://vicerveza.homelinux.net/~viric/soft/ts/) (`ts`).

It generates all parameter combinations, patches each FLUKA input file, submits independent runs to `ts`, and runs a *sentinel* job that waits for all runs in a combo to finish before triggering post-processing.

---

## Features

- **Grid search**: define any number of parameters with lists of values; every combination is run automatically
- **Multiple runs per combo**: configurable number of statistically independent runs (different random seeds)
- **Task spooler integration**: parallelism is controlled via `ts`; no cluster required
- **Automatic post-processing**: runs `usbsuw`, `usbrea`, or any FLUKA post-processing executable after each combo completes
- **Isotope analysis**: reads `RESNUCLEi` binary files, computes activity and decay data, and writes an Excel workbook with per-isotope summaries and pivot tables
- **Resumable**: state is persisted in `state.json`; re-running skips already-completed combos
- **Dry-run mode**: prints all commands without submitting

---

## Requirements

- Python ≥ 3.11
- FLUKA (with `rfluka` on `PATH` or configured via `rfluka_path`)
- [task-spooler](https://vicerveza.homelinux.net/~viric/soft/ts/) (`ts` command)

Install Python dependencies:

```bash
pip install -e .
# or for development:
pip install -e ".[dev]"
```

---

## Quick Start

1. **Write a config file** (see `examples/config.yaml` for a template; copy your `.inp` file next to it):

```yaml
fluka:
  input: my_simulation.inp   # FLUKA input template
  primaries: 10000

output:
  directory: results/

grid:
  parameters:
    beame: [0.05, 0.1, 0.5]  # beam energy values
    mat: [GALLIUM, TUNGSTEN]  # material names
  runs_per_combo: 5           # independent runs per combination

execution:
  max_parallel: 4             # ts concurrency limit

postprocessing:
  ".21":
    executable: usbsuw
  ".22":
    executable: usbrea
```

2. **Launch the grid**:

```bash
python run_grid.py examples/config.yaml
```

A summary table is printed; type `yes` to confirm before jobs are submitted.

3. **Dry run** (print commands only, no submission):

```bash
python run_grid.py examples/config.yaml --dry-run
```

4. **Re-run post-processing** on already-completed data:

```bash
python run_grid.py examples/config.yaml --postprocess
```

5. **Run isotope analysis** (requires an `isotope_analysis` section in config):

```bash
python run_grid.py examples/config.yaml --analyze
```

6. **Reset and start fresh**:

```bash
python run_grid.py examples/config.yaml --reset
```

---

## Project Layout

```
fluka-grid-search/
├── run_grid.py              # CLI entry point
├── README.md
├── examples/
│   └── config.yaml          # Template configuration (copy your .inp file here)
├── grid_search/
│   ├── config.py            # Config loading and validation
│   ├── grid.py              # Parameter combination generation
│   ├── workspace.py         # Per-run directory setup, .inp patching, seed generation
│   ├── state.py             # JSON-backed state manager (resume support)
│   ├── postprocess.py       # Post-processing runner (usbsuw, usbrea, …)
│   ├── resnuclei.py         # RESNUCLEi binary file reader
│   ├── isotope_analysis.py  # Isotope activity analysis and Excel export
│   ├── sentinel.py          # Submitted as a ts job; waits for runs then post-processes
│   └── backends/
│       ├── base.py          # Abstract backend interface
│       └── task_spooler.py  # task-spooler backend
└── tests/                   # pytest test suite (92 tests, local only)
```

---

## How Parameter Patching Works

`run_grid.py` passes `parameters` as a dict to `patch_inp`, which replaces occurrences of each parameter name in the FLUKA `.inp` file with the combo value. Random seeds are also injected per-run.

---

## Running Tests

```bash
pytest
```

---

## License

MIT
