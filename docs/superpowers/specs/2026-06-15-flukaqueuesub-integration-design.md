# FlukaQueueSub as submission engine for fluka-grid-search

**Date:** 2026-06-15
**Status:** Approved (design)

## Goal

Make FlukaQueueSub a dependency of `fluka-grid-search` so the grid search submits FLUKA
jobs through FlukaQueueSub's multi-backend, robust-seed submission system (SLURM / LSF /
HTCondor / Task Spooler) instead of its own task-spooler-only path.

`fluka-grid-search` keeps its "brains" (grid expansion, directory layout, state,
sentinel, post-processing, isotope analysis, `#define` parameter patching).
FlukaQueueSub becomes the submission engine and the source of unique-seed logic.

### Decisions locked during brainstorming

- **Scope:** Full replacement of the submission/backend layer. Grid-search keeps only
  grid expansion + post-processing + isotope analysis + workspace/state.
- **Post-processing scope:** TS auto (keep existing sentinel + auto post-process);
  cluster backends (SLURM/LSF/Condor) are submit-only, user runs `--postprocess` /
  `--analyze` manually after jobs complete.
- **Dependency mechanism:** git submodule.
- **Integration approach:** Approach A — backend-layer adapter, minimal change to
  FlukaQueueSub.

## 1. Dependency wiring

- Add FlukaQueueSub as a git submodule at `fluka-grid-search/external/FlukaQueueSub`.
- FlukaQueueSub is not currently packaged; its modules import each other with bare
  top-level names (`from backends.base import ...`, `from core import ...`). Add a
  minimal `pyproject.toml` to FlukaQueueSub packaging `core` + `backends` (plus root
  scripts as modules) so internal imports keep working unchanged.
- Install editable from the submodule path: `pip install -e external/FlukaQueueSub`.
- grid-search owns its own modules under the `grid_search.*` namespace, so there is no
  top-level collision with grid-search code.
- **Known risk:** bare `core` / `backends` package names could collide with other
  packages on `sys.path`. Future hardening = rename FlukaQueueSub to a `flukaqueuesub/`
  package. Out of scope now (YAGNI).

## 2. What gets replaced vs kept

**Replaced:**
- grid-search seed generation (`grid_search/workspace.py::generate_seed`, naive
  `random.randint`, no cross-run dedup).
- grid-search's job-submission path.

**Kept:**
- grid-search combo loop, `output_dir/<combo>/run_NNNN` directory layout.
- `#define` parameter patching (the whole point of the grid; FlukaQueueSub does not do
  parameter substitution).
- `state.json` management, sentinel, post-processing, isotope analysis.
- grid-search `TaskSpoolerBackend.wait` / `get_exit_code` — TS lifecycle ops the
  sentinel needs; FlukaQueueSub has no equivalent.

So "full replacement" means **submission only**, not the TS wait/poll helpers.

## 3. Adapter — `grid_search/backends/queue_adapter.py`

New module. Uses FlukaQueueSub at **two granularities**, deliberately bypassing
FlukaQueueSub's top-level `_execute_jobs` orchestrator (which would impose its own
`job_N` dir layout and its own `.inp` patching, conflicting with grid-search):

- **Seeds:** `core.fluka.scan_existing_seeds`, `core.fluka.allocate_seed`,
  `core.fluka.find_duplicate_seeds`.
- **Submission:** the `backends.{ts,slurm,lsf,condor}` backend objects — call
  `generate_script` + `submit` per run, fed an `argparse.Namespace` the adapter builds
  from grid-search config, with cwd = grid-search's `run_NNNN` directory.

Per-combo flow replicates FlukaQueueSub's safe 3-phase pattern:
prepare all runs → audit duplicate seeds → submit.

## 4. Config additions (`grid_search/config.py` + yaml)

```yaml
execution:
  backend: ts        # ts | slurm | lsf | condor  (default: ts)
  max_parallel: 4    # ts only
  # cluster params, backend-specific:
  queue: production
  mem: 1500
  time: "1-00:00:00"
  ntasks: 1
  nodes: 1
```

The adapter maps these fields into the FlukaQueueSub `Namespace` expected by each
backend's `generate_script` / `submit` / `validate`.

## 5. Data flow

1. `run_grid` loads config → expand grid → list of combos.
2. Per combo, per run:
   - mkdir `run_NNNN`;
   - patch `#define` params + primaries into `run.inp` (grid-search `patch_inp`,
     parameter substitution path retained);
   - allocate a **unique** seed via FlukaQueueSub allocator (scans the whole output
     dir for existing seeds); write the `RANDOMIZ` card.
3. **Seed audit:** `find_duplicate_seeds` over the output dir → abort if any duplicate.
   Runs **both** at launch (pre-submit) and standalone (`check_seeds`).
4. Submit each run via the selected FlukaQueueSub backend → job-id (TS) or descriptive
   id (cluster) → record in `state.json`.
5. Branch on backend:
   - `ts`: submit `sentinel.py` as a ts job depending on the run job-ids → waits →
     post-process → isotope analysis (existing flow, unchanged).
   - cluster (`slurm`/`lsf`/`condor`): submit-only. User runs `--postprocess` /
     `--analyze` after the jobs finish.

## 6. Error handling

- Missing backend client tool (`sbatch` / `bsub` / `condor_submit` / `ts`) → clear
  error, abort.
- Duplicate seed detected → abort before any submission.
- FLUKA path resolution via FlukaQueueSub `fluka.detect_fluka_path` (reused).
- Per-run submit failure → log, mark that run failed in `state.json`, continue with the
  remaining runs (FlukaQueueSub's existing per-job tolerance).
- Cluster backend + auto post-process requested → unsupported; warn and point user to
  manual `--postprocess`.

## 7. Testing

- Adapter unit: correct `Namespace` built per backend from grid config (mocked).
- Seed integration: no duplicate seeds across combos/runs using the FlukaQueueSub
  allocator.
- Existing TS grid tests stay green on the new submission path.
- Cluster backends: dry-run emits correct scripts/commands (mock `subprocess`).
- Submodule import smoke test.

## 8. Non-goals

- No cluster auto-post-processing (manual, deferred).
- No isotope-analysis feature changes.
- No FlukaQueueSub internal rewrite (only add `pyproject.toml` for packaging).
