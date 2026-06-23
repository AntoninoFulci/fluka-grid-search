# fluka-grid-search

A Python tool that generates FLUKA Monte Carlo input files over a parameter grid
and submits them to the farm via [FlukaQueueSub](https://github.com/AntoninoFulci/FlukaQueueSub).

It generates all parameter combinations, patches each FLUKA input file with unique
random seeds, and submits the independent runs through FlukaQueueSub (task-spooler or
a cluster scheduler). **Queue monitoring, post-processing and isotope analysis are
not handled here** — monitoring/submission lives in FlukaQueueSub, and RESNUCLEi
post-processing + isotope analysis live in
[FlukaIsotopeAnalysis](https://github.com/AntoninoFulci/FlukaIsotopeAnalysis).

---

## Features

- **Grid search**: define any number of parameters with lists of values; every combination is generated automatically
- **Multiple runs per combo**: configurable number of statistically independent runs (different random seeds)
- **Unique seeds**: `RANDOMIZ` seeds are unique across the whole grid; duplicates abort submission and can be audited with `--check-seeds`
- **Multi-backend submission**: delegates to FlukaQueueSub (`ts` / `slurm` / `lsf` / `condor`)
- **Dry-run mode**: prints what would be submitted without submitting

---

## Requirements

- Python ≥ 3.11
- FLUKA (with `rfluka` on `PATH` or configured via `rfluka_path`)
- FlukaQueueSub submodule (provides the submission backends)
- For the `ts` backend: [task-spooler](https://vicerveza.homelinux.net/~viric/soft/ts/) (`ts` command)

### Submodules

This project uses two git submodules under `external/`:

- `FlukaQueueSub` — multi-backend job submission (used at submit time)
- `FlukaIsotopeAnalysis` — RESNUCLEi post-processing + isotope/activation analysis (used after jobs finish)

Clone with submodules and install everything editable:

```bash
git clone --recurse-submodules <repo-url>
cd fluka-grid-search
pip install -e .
pip install -e external/FlukaQueueSub
pip install -e external/FlukaIsotopeAnalysis
# for development:
pip install -e ".[dev]"
```

After the jobs finish, post-process and analyse a simulation directory with the
standalone tool:

```bash
python external/FlukaIsotopeAnalysis/run_analysis.py analysis.yaml
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
  backend: ts                 # ts (default) | slurm | lsf | condor
  max_parallel: 4             # ts slot count (local concurrency)
```

2. **Launch the grid** (generate inputs + submit):

```bash
python run_grid.py examples/config.yaml
```

A summary table is printed; type `yes` to confirm before jobs are submitted.

3. **Dry run** (print what would be submitted, no submission):

```bash
python run_grid.py examples/config.yaml --dry-run
```

4. **Audit seeds** for duplicates:

```bash
python run_grid.py examples/config.yaml --check-seeds
```

5. **Reset and start fresh** (deletes the output directory):

```bash
python run_grid.py examples/config.yaml --reset
```

---

## Backends (ts / SLURM / LSF / HTCondor)

All submission is delegated to the FlukaQueueSub submodule. Select the backend in the config:

```yaml
execution:
  backend: slurm   # ts (default) | slurm | lsf | condor
  queue: production
  mem: "2000"
  time: "2-00:00:00"
```

Every backend is **submit-only** from this tool's perspective: `run_grid.py` generates
the input files and hands each run to FlukaQueueSub. Waiting for jobs, status, and
post-processing are FlukaQueueSub / FlukaIsotopeAnalysis concerns.

**Seed uniqueness** is enforced across the whole grid for every backend.

**Limitation:** `fluka.use_dpm` is currently rejected — the FlukaQueueSub backends do
not emit `rfluka -d`. Add DPM support to FlukaQueueSub to restore it.

---

## Project Layout

```
fluka-grid-search/
├── run_grid.py              # CLI entry point: generate inputs + submit
├── README.md
├── pyproject.toml
├── examples/
│   └── config.yaml          # Template configuration (copy your .inp file here)
├── grid_search/
│   ├── config.py            # Config loading and validation
│   ├── grid.py              # Parameter combination generation
│   ├── workspace.py         # Per-run directory setup, .inp patching
│   ├── seeds.py             # RANDOMIZ seed generation + duplicate audit
│   └── backends/
│       └── queue_adapter.py # Adapter to FlukaQueueSub backends (ts/slurm/lsf/condor)
├── external/
│   ├── FlukaQueueSub/        # submodule: job submission
│   └── FlukaIsotopeAnalysis/ # submodule: post-processing + isotope analysis
└── tests/                   # pytest test suite (local only)
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
