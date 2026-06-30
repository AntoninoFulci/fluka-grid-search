# fluka-grid-search

Generate FLUKA Monte Carlo input files over a parameter grid and submit them to the
farm. This is the **front end** of a three-project workflow:

| Project | Role |
|---------|------|
| **fluka-grid-search** (this repo) | generate input files for every parameter combination + submit them |
| [FlukaQueueSub](https://github.com/AntoninoFulci/FlukaQueueSub) | submission backends (task-spooler / SLURM / LSF / HTCondor) + queue monitoring |
| [FlukaIsotopeAnalysis](https://github.com/AntoninoFulci/FlukaIsotopeAnalysis) | post-process `RESNUCLEi` output + isotope/activation analysis to Excel |

This repo does **one job**: take a FLUKA `.inp` template, expand a parameter grid,
patch each combination with unique random seeds, and hand the runs to FlukaQueueSub.

---

## Workflow at a glance

```
   config.yaml + template.inp
              │
              ▼
   python run_grid.py config.yaml          (this repo: generate + submit)
              │   creates results/<combo>/run_NNNN/simulation_NNNN.inp
              │   and submits each run via FlukaQueueSub
              ▼
   jobs run on the farm                     (FlukaQueueSub backend: ts/slurm/lsf/condor)
              │   each run produces RESNUCLEi binaries (fort.21, …)
              ▼
   python external/FlukaIsotopeAnalysis/run_analysis.py analysis.yaml
                                            (FlukaIsotopeAnalysis: usrsuw + isotopes → .xlsx)
```

---

## Setup (no installation required)

Requires Python ≥ 3.10, FLUKA (`rfluka` on `PATH` or set via `rfluka_path`), and —
for the `ts` backend — [task-spooler](https://vicerveza.homelinux.net/~viric/soft/ts/).

You do **not** need to `pip install` any of the three projects. Just clone with
submodules and run the scripts directly — `run_grid.py` puts the repo and the
bundled FlukaQueueSub submodule on `sys.path` automatically.

```bash
git clone --recurse-submodules <repo-url>
cd fluka-grid-search
# already cloned without --recurse-submodules?
git submodule update --init --recursive

# install only the third-party Python libraries (not the projects themselves):
pip install pyyaml colorama tabulate rich pandas openpyxl periodictable radioactivedecay

python run_grid.py examples/config.yaml --dry-run
```

(If you prefer, the projects can still be installed editable with
`pip install -e .` — but it is not required.)

---

## Step 1 — Prepare your FLUKA input template

`run_grid.py` patches a normal FLUKA `.inp` file. The template must contain:

- A `#define NAME value` line for **every** grid parameter (the value is replaced per combo):
  ```
  #define beame 0.1
  #define mat   GALLIUM
  ```
- A `RANDOMIZ` card (rewritten per run with a unique seed):
  ```
  RANDOMIZ          1.0
  ```
- A `START` card (its primary count is overwritten when `fluka.primaries` is set):
  ```
  START         10000.
  ```

If a grid parameter has no matching `#define`, submission aborts with a clear error.

---

## Step 2 — Write the config

See [`examples/config.yaml`](examples/config.yaml) for a fully annotated template, and
[`examples/config_slurm.yaml`](examples/config_slurm.yaml) for a cluster example.

```yaml
fluka:
  input: simulation.inp      # FLUKA .inp template (relative paths are resolved next to this config)
  primaries: 10000           # optional: overrides the START primary count
  rfluka_path: null          # optional: FLUKA bin dir; null → discovered via `fluka-config --bin`
  custom_executable: null    # optional: passed to rfluka as `-e <exe>`

output:
  directory: results/        # where run dirs + patched inputs are written

grid:
  parameters:                # each key must match a `#define` in the template
    beame: [0.05, 0.1, 0.5]
    mat: [GALLIUM, TUNGSTEN]
  runs_per_combo: 5          # statistically independent runs per combination (unique seeds)

execution:
  backend: ts                # ts (default) | slurm | lsf | condor
  max_parallel: 4            # ts slot count (local concurrency)
  # cluster-only fields (slurm/lsf/condor):
  queue: production          # slurm partition / lsf queue / condor universe
  mem: "2000"
  time: "2-00:00:00"         # slurm/lsf wall time
  ntasks: 1
  nodes: 1                   # slurm
  gres: "disk:1G"            # slurm
  ncpu: 1                    # condor
  disk: 100000               # condor request_disk (kB)
  condor_max_runtime: 86400  # condor +MaxRuntime (s)
```

Total jobs submitted = (product of parameter list lengths) × `runs_per_combo`.

---

## Step 3 — Generate and submit

```bash
# Dry run: print what would be submitted, submit nothing
python run_grid.py examples/config.yaml --dry-run

# Real run: prints a summary table, asks for confirmation, then submits
python run_grid.py examples/config.yaml

# Audit the output dir for duplicate RANDOMIZ seeds
python run_grid.py examples/config.yaml --check-seeds

# Delete the output directory and start fresh (asks for confirmation)
python run_grid.py examples/config.yaml --reset
```

### What it produces

```
results/
└── beame0.05_matGALLIUM/         # one dir per parameter combination
    ├── run_0001/
    │   └── simulation_0001.inp    # patched template (combo values + unique seed)
    ├── run_0002/
    └── ...
```

Seeds are unique across the **whole** output directory; if a duplicate is detected,
submission aborts before any job is sent.

> **Note:** there is no resume/state tracking. Re-running submits everything again —
> use `--reset` to start clean. Seed uniqueness is still guaranteed.

---

## Step 4 — Monitor (FlukaQueueSub)

Job status, waiting, and queue management are handled by **FlukaQueueSub** (see its
README). `run_grid.py` only submits; it does not wait or report progress.

---

## Step 5 — Post-process and analyse (FlukaIsotopeAnalysis)

Once the runs finish, each produces `RESNUCLEi` binaries. Use the standalone tool to
merge them (via `usrsuw`) and compute isotope activity into an Excel workbook:

```bash
python external/FlukaIsotopeAnalysis/run_analysis.py analysis.yaml
```

Example `analysis.yaml`:

```yaml
analysis:
  directory: results/beame0.05_matGALLIUM/run_0001  # folder with fort.21… and/or .rnc files
  units: [21, 22, 23]                               # FLUKA RESNUCLEi unit numbers
  volume: 1000                                      # cm³
  isotopes:                                         # Z: A
    31: 70
    30: 69
  output: isotopes.xlsx
```

It auto-detects already-processed `.rnc` files (e.g. from FLAIR) and only runs `usrsuw`
on raw units that need it. See the FlukaIsotopeAnalysis README for details.

---

## Backends

All submission is delegated to FlukaQueueSub. Choose via `execution.backend`:

| backend | notes |
|---------|-------|
| `ts` (default) | task-spooler; `max_parallel` sets the local slot count (`ts -S`) |
| `slurm` | uses `queue`/`mem`/`time`/`ntasks`/`nodes`/`gres` |
| `lsf` | uses `queue`/`mem`/`time`/`ntasks` |
| `condor` | uses `queue`/`mem`/`ncpu`/`disk`/`condor_max_runtime` |

**Limitation:** `fluka.use_dpm` is currently rejected — the FlukaQueueSub backends do
not emit `rfluka -d`. Add DPM support to FlukaQueueSub to restore it.

---

## Project Layout

```
fluka-grid-search/
├── run_grid.py              # CLI entry point: generate inputs + submit
├── pyproject.toml
├── examples/
│   ├── config.yaml          # annotated ts example
│   └── config_slurm.yaml    # cluster example
├── grid_search/
│   ├── config.py            # config loading + validation
│   ├── grid.py              # parameter combination generation
│   ├── workspace.py         # per-run dir setup + .inp patching
│   ├── seeds.py             # RANDOMIZ seed generation + duplicate audit
│   └── backends/
│       └── queue_adapter.py # adapter to FlukaQueueSub backends
└── external/
    ├── FlukaQueueSub/        # submodule: submission + monitoring
    └── FlukaIsotopeAnalysis/ # submodule: post-processing + analysis
```

---

## Running Tests

```bash
pytest
```

---

## License

MIT
