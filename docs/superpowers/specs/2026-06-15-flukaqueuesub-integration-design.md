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

- **Scope (refined):** ADD the cluster backends grid-search lacks (SLURM/LSF/Condor)
  via FlukaQueueSub; **keep grid-search's existing Task Spooler path unchanged**;
  replace grid-search's naive seed generation globally with FlukaQueueSub's robust
  seed primitives. Grid-search keeps grid expansion, post-processing, isotope analysis,
  workspace/state, sentinel.
- **Post-processing scope:** TS auto (keep existing sentinel + auto post-process);
  cluster backends (SLURM/LSF/Condor) are submit-only, user runs `--postprocess` /
  `--analyze` manually after jobs complete.
- **Dependency mechanism:** git submodule.
- **Integration approach:** Approach A — backend-layer adapter, minimal change to
  FlukaQueueSub.

### Why "full replacement of TS submission" was rejected (findings from API review)

Verifying real signatures before planning surfaced three frictions:

1. **Seed scan is layout-locked.** FlukaQueueSub `scan_existing_seeds` /
   `find_duplicate_seeds` (`core/fluka.py::_seed_map`) glob `output_dir/job_*/*.inp`.
   Grid-search uses `output_dir/<combo>/run_NNNN/*.inp` — different prefix, deeper.
   They will not find grid-search's seeds. Reuse only the layout-agnostic primitives
   `parse_randomiz` + `allocate_seed`; grid-search supplies its own tree scanner.
2. **FlukaQueueSub backends do not support `use_dpm`.** Every backend builds
   `rfluka -M 1 [-e custom_exe]`. Grid-search's recent `use_dpm` feature emits
   `rfluka -d` (`run_grid.py`). Routing submission through FlukaQueueSub drops dpm.
3. **TS is already solved in grid-search and the sentinel depends on it.**
   Grid-search `TaskSpoolerBackend` returns the ts job-id the sentinel waits on, does
   `wait` / `get_exit_code` / `set_max_parallel`, and runs rfluka with `cwd=run_dir`.
   FlukaQueueSub's `TSBackend.submit` builds its own command, has no `cwd` control
   (runs in the current dir, breaking per-run isolation) and no dpm. It is strictly
   worse for grid-search than the existing TS backend.

Conclusion: the value FlukaQueueSub actually adds is the cluster backends grid-search
lacks plus robust seeds — so we ADD those rather than replacing a working TS path.

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
  `random.randint`, no cross-run dedup) — replaced **globally** (all backends, TS
  included) with FlukaQueueSub `parse_randomiz` + `allocate_seed` wrapped by a
  grid-search tree scanner.

**Added:**
- Cluster submission backends (SLURM / LSF / HTCondor) via a new adapter that drives
  FlukaQueueSub's backend objects. Submit-only.

**Kept unchanged:**
- grid-search combo loop, `output_dir/<combo>/run_NNNN` directory layout.
- `#define` parameter patching (FlukaQueueSub does not do parameter substitution).
- `state.json` management, sentinel, post-processing, isotope analysis.
- grid-search `TaskSpoolerBackend` (submit + `wait` + `get_exit_code` +
  `set_max_parallel`) and the entire TS submit + sentinel flow.

## 3. Components

### 3a. Seed module — `grid_search/seeds.py` (new)

Layout-aware wrapper over FlukaQueueSub primitives, used by **every** backend:

- `scan_used_seeds(output_dir: Path) -> set[int]` — glob `output_dir/*/run_*/*.inp`,
  call FlukaQueueSub `parse_randomiz` on each, collect.
- `next_seed(used: set[int]) -> int` — thin wrapper over FlukaQueueSub `allocate_seed`
  (mutates `used`, returns a fresh seed).
- `find_duplicate_seeds(output_dir: Path) -> dict[int, list[Path]]` — grid-tree
  duplicate map (parallels FlukaQueueSub's, but over the grid layout); used both at
  launch (pre-submit, abort on dup) and by the standalone `check_seeds` entry point.

### 3b. Cluster adapter — `grid_search/backends/queue_adapter.py` (new)

Drives FlukaQueueSub's `backends.{slurm,lsf,condor}` objects. Bypasses FlukaQueueSub's
top-level `_execute_jobs` (which would impose its own `job_N` layout + patching). For
each run the adapter:

- builds an `argparse.Namespace` from grid-search config (backend-specific params);
- builds a FlukaQueueSub `JobInfo(input_file, iteration, fluka_path, custom_exe)`;
- calls `backend.validate(ns)`, `backend.generate_script(job_info, run_dir, ns)`,
  `backend.submit(script_path, job_info, ns)` → returns the backend job-id string,
  recorded in `state.json`.

The `.inp` is already patched (params + seed + primaries) by grid-search before the
adapter is called, so the adapter does no patching.

### 3c. TS path — unchanged

`run_grid.py::_submit_combo` keeps using grid-search's `TaskSpoolerBackend` and the
sentinel. Only its seed call changes (uses 3a instead of `workspace.generate_seed`).

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
   - allocate a **unique** seed via `seeds.next_seed` over the set returned by
     `seeds.scan_used_seeds(output_dir)`; `patch_inp` writes the `RANDOMIZ` card.
3. **Seed audit:** `seeds.find_duplicate_seeds(output_dir)` → abort if any duplicate.
   Runs **both** at launch (pre-submit) and standalone (`check_seeds`).
4. Branch on `config.execution.backend`:
   - `ts`: existing `_submit_combo` path — submit each run via grid-search
     `TaskSpoolerBackend` (cwd=run_dir, dpm-aware), then submit `sentinel.py` as a ts
     job on the run job-ids → waits → post-process → isotope analysis. **Unchanged
     except the seed call.**
   - cluster (`slurm`/`lsf`/`condor`): `queue_adapter` submits each run via the
     FlukaQueueSub backend → job-id recorded in `state.json`. Submit-only; no sentinel.
     User runs `--postprocess` / `--analyze` after the jobs finish.

## 6. Error handling

- Missing backend client tool (`sbatch` / `bsub` / `condor_submit` / `ts`) →
  `subprocess` raises; surface a clear error, abort.
- Duplicate seed detected → abort before any submission.
- FLUKA path: TS path uses grid-search `_resolve_rfluka`; cluster path uses
  FlukaQueueSub `fluka.detect_fluka_path` (returns `(bin, folder)`), passed into
  `JobInfo.fluka_path`.
- Per-run submit failure (cluster) → log, mark that run failed in `state.json`,
  continue with remaining runs.
- **`use_dpm` + cluster backend** → unsupported (FlukaQueueSub backends cannot emit
  `rfluka -d`). `validate_config` raises a clear error. Documented limitation.
- Cluster backend → post-processing is never auto-run; `_submit_combo` for cluster
  prints a reminder to run `--postprocess` after jobs complete.

## 7. Testing

- Seed module: `scan_used_seeds` finds seeds in the `combo/run_*` tree;
  `next_seed` never returns a used seed; `find_duplicate_seeds` flags planted dups.
- Adapter unit: correct `Namespace` + `JobInfo` built per backend from grid config;
  `generate_script` / `submit` called with expected args (mocked backend).
- Existing TS grid tests stay green (TS path unchanged beyond the seed call).
- Cluster backends: dry-run path returns the `[dry run] ...` string without invoking
  `sbatch` / `bsub` / `condor_submit` (mock `subprocess`).
- `validate_config` raises on `use_dpm` + cluster backend.
- Submodule import smoke test (`from core.fluka import allocate_seed`).

## 8. Non-goals

- No cluster auto-post-processing (manual, deferred).
- No cluster `use_dpm` support (errors out; documented limitation).
- No isotope-analysis feature changes.
- No FlukaQueueSub internal rewrite (only add `pyproject.toml` for packaging).
- No replacement of the working TS submission path.
