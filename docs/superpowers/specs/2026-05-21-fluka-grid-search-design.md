# FLUKA Grid Search Framework — Design Spec

**Date:** 2026-05-21  
**Status:** Approved

---

## Overview

A Python framework for running grid searches over FLUKA simulation parameters on a local Mac using `task-spooler` (`ts`) as the execution backend. Designed to be resumable, backend-agnostic, and extensible to HPC clusters in the future.

---

## Architecture

Five Python modules plus one standalone sentinel script:

```
run_grid.py              ← CLI entry point
grid_search/
  config.py              ← load & validate config.yaml
  grid.py                ← generate all parameter combinations
  workspace.py           ← create working dirs, patch .inp files, generate seeds
  state.py               ← read/write state.json (resumability)
  postprocess.py         ← drive usbsuw/usbrea via stdin
  backends/
    base.py              ← abstract ExecutionBackend interface
    task_spooler.py      ← TaskSpoolerBackend (submits via ts)
sentinel.py              ← standalone script submitted as a ts job per combo
```

### Execution flow

1. `run_grid.py` loads and validates config, discovers `rfluka` path via `fluka-config --bin` (or uses override).
2. For each parameter combination × N runs: create `results/<combo_name>/run_NNNN/`, write patched `.inp` with substituted `#define` values and fresh random seed.
3. Submit N `rfluka` jobs to `ts` for the combo.
4. Submit one `sentinel.py` job per combo to `ts` (after the N run jobs). The orchestrator then exits — `ts` carries everything forward.
5. The sentinel waits for each run job to finish, collects successful output files, runs post-processing tools, and updates `state.json`.

---

## Config Format

```yaml
fluka:
  input: 2026-01-23_Frascati_V1.inp
  custom_executable: ./myfluka   # optional — passed to rfluka -e
  rfluka_path: null              # null = auto-detect via fluka-config --bin

output:
  directory: results/

grid:
  parameters:
    beame: [0.05, 0.1, 0.5]
    mat: [GALLIUM, TUNGSTEN]
  runs_per_combo: 5

execution:
  max_parallel: 4                # passed to ts -S (max simultaneous ts slots)

postprocessing:
  ".21":
    executable: usbsuw
  ".22":
    executable: usbrea
```

---

## Parameter Substitution

The `.inp` file uses FLUKA's preprocessor syntax:

```
#define beame 0.5
...
BEAM          $beame
```

The framework patches `#define <name> <value>` lines using targeted regex replacement — no full template engine. The `RANDOMIZ` line receives a fresh `random.randint(1, int(9e7))` seed per run (same approach as `FlukaQueueSub/scripts/launch_jobs_ts.py`).

**Validation on startup:** for each parameter name in `grid.parameters`, the framework checks that a matching `#define <name>` exists in the `.inp` file and raises an error if not.

---

## Output Directory Structure

```
results/
  state.json
  beame0.05_matGALLIUM/
    run_0001/
      simulation_0001.inp
      <fluka output files>
    run_0002/
      ...
    postproc/
      merged.21
      usbsuw.log
  beame0.1_matGALLIUM/
    ...
```

Combo directory names are built from `param_name + value` pairs joined by `_`, e.g. `beame0.05_matGALLIUM`.

---

## State Management

`state.json` lives in the output directory:

```json
{
  "beame0.05_matGALLIUM": {
    "status": "running",
    "parameters": {"beame": 0.05, "mat": "GALLIUM"},
    "runs": {
      "run_0001": {"ts_job_id": 12, "status": "done", "exit_code": 0},
      "run_0002": {"ts_job_id": 13, "status": "running"},
      "run_0003": {"ts_job_id": 14, "status": "pending"}
    },
    "sentinel_ts_job_id": 17
  }
}
```

**Combo statuses:** `pending → submitted → postprocessing → done | partial`

- `done`: all runs succeeded, post-processing complete
- `partial`: some runs failed, post-processing ran on successful subset

**Resumability:** on re-run, the orchestrator reads `state.json`, skips `done` combos, and re-submits anything still `pending`. Combos in `submitted`/`running` state are left to their sentinel — the orchestrator never double-submits.

---

## Sentinel

After submitting N run jobs for a combo, the orchestrator submits:

```
ts python sentinel.py config.yaml results/ beame0.05_matGALLIUM 12 13 14 15 16
```

The sentinel receives the config path so it can read the `postprocessing` section (which tools to run for which extensions).

The sentinel script:
1. Calls `ts -w <id>` for each run job ID — blocks until each finishes.
2. Reads exit codes via `ts -i <id>`, marks failed runs in `state.json`.
3. Collects output files from successful runs (e.g. all `*.21` files in their run dirs).
4. For each extension in `postprocessing` config: launches the tool, feeds file paths one per line via stdin followed by a blank line to trigger processing.
5. Saves merged output and logs to `postproc/`.
6. Updates `state.json`: combo → `done` or `partial`.

Post-processing tools are driven like this (matching FLUKA's interactive stdin protocol):

```python
input_data = "\n".join(file_paths) + "\n\n"
subprocess.run([executable], input=input_data, text=True, cwd=postproc_dir,
               capture_output=True)
```

---

## Failure Handling

If one or more runs fail (non-zero exit code):
- Failed runs are marked in `state.json` with their exit code.
- Post-processing runs on the successful subset.
- Combo is marked `partial` rather than `done`.
- A clear summary is printed at the end listing all partial/failed combos.

---

## CLI Interface

```bash
# Normal run (submit all, or resume if state.json exists)
python run_grid.py config.yaml

# Reset output dir and start fresh (prompts for confirmation)
python run_grid.py config.yaml --reset

# Re-run post-processing only on already-completed runs
python run_grid.py config.yaml --postprocess

# Re-run post-processing for one specific combo
python run_grid.py config.yaml --postprocess --combo beame0.05_matGALLIUM

# Dry run — print what would be submitted, no actual ts calls
python run_grid.py config.yaml --dry-run
```

`--reset` and `--postprocess` are mutually exclusive.

---

## Backend Abstraction

```python
class ExecutionBackend:
    def submit(self, command: list[str], working_dir: Path) -> str:
        """Submit a job. Returns backend-specific job ID."""
        ...

    def wait(self, job_id: str) -> int:
        """Block until job completes. Returns exit code."""
        ...

    def get_exit_code(self, job_id: str) -> int:
        """Get exit code of a completed job."""
        ...

    def set_max_parallel(self, n: int) -> None:
        """Set maximum simultaneous jobs."""
        ...
```

`TaskSpoolerBackend` implements this using `ts`. Future backends (`SlurmBackend`, `CondorBackend`) implement the same interface.

---

## Key Implementation Notes

- **No `os.chdir()`** — all subprocess calls use the `cwd=` argument. The existing `launch_jobs_ts.py` uses `os.chdir()` which is unsafe in concurrent contexts; this framework avoids it entirely.
- **`ts -S <n>`** sets max parallel slots globally; call once at startup.
- **`rfluka` path** is resolved once at startup and passed through; never re-resolved per job.
- The sentinel is a standalone script (not a module) so it can be submitted to `ts` without import path concerns.
