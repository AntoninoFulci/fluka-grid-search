# DPM launch option (`rfluka -d`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let runs launch with the DPMJET/RQMD executable via `rfluka -d`, configurable in both FlukaQueueSub and fluka-grid-search, mutually exclusive with the custom executable (`-e`).

**Architecture:** Add a boolean `use_dpm` to FlukaQueueSub's `JobInfo`; each backend emits `-d` (else `-e <exe>`). Expose it in FlukaQueueSub's CLI (`-D/--dpm`) and YAML config, and in grid-search's config which forwards it through `queue_adapter` into `JobInfo`. Mutual exclusivity is validated in both projects.

**Tech Stack:** Python ≥3.10, argparse, pyyaml, pytest. Run from source (no install).

**Reference spec:** `docs/superpowers/specs/2026-06-24-dpm-launch-option-design.md`

## Global Constraints

- Two repos: FlukaQueueSub at `/Users/tonyf/Work/fluka-grid-search/external/FlukaQueueSub`, grid-search at `/Users/tonyf/Work/fluka-grid-search`.
- Install-free: tests rely on a root `conftest.py` putting the repo on `sys.path` (grid-search already has one; FlukaQueueSub gets one in Task 1).
- In both repos `tests/` is gitignored — test files are local-only (not committed); `conftest.py` IS tracked.
- DPM flag spelling: CLI `-D, --dpm`; YAML key `use_dpm: true`. `-d` stays `--output-dir` in `launch_jobs.py`.
- `use_dpm` and the custom executable are mutually exclusive everywhere.

---

# PHASE A — FlukaQueueSub

> CWD for Phase A: `/Users/tonyf/Work/fluka-grid-search/external/FlukaQueueSub` (call it `$Q`).

## Task 1: `JobInfo.use_dpm` + backends emit `-d`

**Files:**
- Modify: `$Q/backends/base.py` (JobInfo)
- Modify: `$Q/backends/ts.py`, `$Q/backends/slurm.py`, `$Q/backends/lsf.py`, `$Q/backends/htcondor.py`
- Create: `$Q/conftest.py` (tracked; path shim for tests)
- Test: `$Q/tests/test_dpm_command.py` (local-only)

**Interfaces:**
- Produces: `JobInfo(input_file, iteration, fluka_path, custom_exe, use_dpm=False)`; every backend's `submit`/`generate_script` emits `rfluka -M 1 -d` when `use_dpm` is True, `-e <exe>` when only `custom_exe` is set, neither otherwise.

- [ ] **Step 1: Add the path-shim conftest (enables install-free tests)**

Create `$Q/conftest.py`:
```python
import sys
from pathlib import Path

# Run tests without installing: put this repo on sys.path for `backends` / `core`.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
```

- [ ] **Step 2: Write the failing test**

Create `$Q/tests/test_dpm_command.py`:
```python
from argparse import ArgumentParser
from pathlib import Path

from backends.base import JobInfo
from backends.ts import TSBackend
from backends.slurm import SlurmBackend
from backends.lsf import LSFBackend
from backends.htcondor import HTCondorBackend


def _args(backend, **over):
    p = ArgumentParser()
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=False)
    backend.add_args(p)
    ns = p.parse_args([])
    for k, v in over.items():
        setattr(ns, k, v)
    return ns


def _ji(**over):
    base = dict(input_file="sim.inp", iteration=1, fluka_path="/fluka/bin",
                custom_exe=None, use_dpm=False)
    base.update(over)
    return JobInfo(**base)


# --- ts: command list via dry-run string ---

def test_ts_dpm():
    cmd = TSBackend().submit(None, _ji(use_dpm=True), _args(TSBackend(), dry_run=True))
    assert "-d" in cmd.split()
    assert "-e" not in cmd.split()


def test_ts_custom():
    cmd = TSBackend().submit(None, _ji(custom_exe="./myfluka"), _args(TSBackend(), dry_run=True))
    assert "-e ./myfluka" in cmd
    assert "-d" not in cmd.split()


def test_ts_standard():
    cmd = TSBackend().submit(None, _ji(), _args(TSBackend(), dry_run=True))
    assert "-d" not in cmd.split()
    assert "-e" not in cmd.split()


# --- cluster backends: command embedded in generated script ---

def _script(backend, job_info, tmp_path):
    path = backend.generate_script(job_info, str(tmp_path), _args(backend))
    return Path(path).read_text()


def test_slurm_dpm(tmp_path):
    txt = _script(SlurmBackend(), _ji(use_dpm=True), tmp_path)
    assert "rfluka -M 1 -d" in txt
    assert " -e " not in txt


def test_lsf_dpm(tmp_path):
    txt = _script(LSFBackend(), _ji(use_dpm=True), tmp_path)
    assert "rfluka -M 1 -d" in txt
    assert " -e " not in txt


def test_htcondor_dpm(tmp_path):
    txt = _script(HTCondorBackend(), _ji(use_dpm=True), tmp_path)
    assert "rfluka -M 1 -d" in txt
    assert " -e " not in txt


def test_slurm_custom(tmp_path):
    txt = _script(SlurmBackend(), _ji(custom_exe="./myfluka"), tmp_path)
    assert "-e ./myfluka" in txt
    assert "rfluka -M 1 -d" not in txt
```

- [ ] **Step 3: Run the test, verify it fails**

Run: `cd /Users/tonyf/Work/fluka-grid-search/external/FlukaQueueSub && python -m pytest tests/test_dpm_command.py -q`
Expected: FAIL — `TypeError: JobInfo.__init__() got an unexpected keyword argument 'use_dpm'`.

- [ ] **Step 4: Add `use_dpm` to `JobInfo`**

In `$Q/backends/base.py`, change the dataclass:
```python
@dataclass
class JobInfo:
    input_file: str
    iteration: int
    fluka_path: str
    custom_exe: str | None
    use_dpm: bool = False
```

- [ ] **Step 5: Emit `-d` in `ts.py`**

In `$Q/backends/ts.py`, replace:
```python
        fluka_parts = ["rfluka", "-M", "1"]
        if job_info.custom_exe is not None:
            fluka_parts.extend(["-e", job_info.custom_exe])
        fluka_parts.append(job_info.input_file)
```
with:
```python
        fluka_parts = ["rfluka", "-M", "1"]
        if job_info.use_dpm:
            fluka_parts.append("-d")
        elif job_info.custom_exe is not None:
            fluka_parts.extend(["-e", job_info.custom_exe])
        fluka_parts.append(job_info.input_file)
```

- [ ] **Step 6: Emit `-d` in the three cluster backends**

In each of `$Q/backends/slurm.py`, `$Q/backends/lsf.py`, `$Q/backends/htcondor.py`, replace this block inside `generate_script`:
```python
        fluka_cmd = f"{job_info.fluka_path}/rfluka -M 1"
        if job_info.custom_exe is not None:
            fluka_cmd += f" -e {job_info.custom_exe}"
```
with:
```python
        fluka_cmd = f"{job_info.fluka_path}/rfluka -M 1"
        if job_info.use_dpm:
            fluka_cmd += " -d"
        elif job_info.custom_exe is not None:
            fluka_cmd += f" -e {job_info.custom_exe}"
```

- [ ] **Step 7: Run the test, verify it passes**

Run: `cd /Users/tonyf/Work/fluka-grid-search/external/FlukaQueueSub && python -m pytest tests/test_dpm_command.py -q`
Expected: PASS (8 passed).

- [ ] **Step 8: Commit**

```bash
cd /Users/tonyf/Work/fluka-grid-search/external/FlukaQueueSub
git add backends/base.py backends/ts.py backends/slurm.py backends/lsf.py backends/htcondor.py conftest.py
git commit -m "feat: JobInfo.use_dpm — backends emit rfluka -d (mutually exclusive with -e)"
```
(Note: `tests/` is gitignored, so the test file is intentionally not committed.)

---

## Task 2: CLI `--dpm` + YAML `use_dpm` + mutual-exclusivity

**Files:**
- Modify: `$Q/launch_jobs.py` (subparser arg, validation, JobInfo build, summary row)
- Modify: `$Q/core/config.py` (YAML parser arg + ME check)
- Test: `$Q/tests/test_dpm_cli.py` (local-only)

**Interfaces:**
- Consumes: `JobInfo(..., use_dpm=...)` from Task 1.
- Produces: `launch_jobs` accepts `-D/--dpm` (dest `use_dpm`); `core.config.load_yaml_config` recognises `use_dpm: true`; both reject `use_dpm` + `custom_exe` together with a clear error.

- [ ] **Step 1: Write the failing test**

Create `$Q/tests/test_dpm_cli.py`:
```python
import pytest

import launch_jobs
from core.config import load_yaml_config
from launch_jobs import BACKENDS


def test_parser_accepts_dpm():
    parser = launch_jobs._build_parser()
    args = parser.parse_args(["ts", "-f", "sim.inp", "-n", "2", "--dpm"])
    assert args.use_dpm is True
    assert args.custom_exe is None


def test_parser_dpm_default_false():
    parser = launch_jobs._build_parser()
    args = parser.parse_args(["ts", "-f", "sim.inp", "-n", "2"])
    assert args.use_dpm is False


def test_yaml_config_reads_use_dpm(tmp_path):
    cfg = tmp_path / "job.yaml"
    cfg.write_text("backend: ts\ninput: sim.inp\nnjobs: 2\nuse_dpm: true\n")
    ns = load_yaml_config(str(cfg), BACKENDS)
    assert ns.use_dpm is True


def test_yaml_config_rejects_dpm_plus_custom(tmp_path):
    cfg = tmp_path / "job.yaml"
    cfg.write_text(
        "backend: ts\ninput: sim.inp\nnjobs: 2\nuse_dpm: true\ncustom_exe: ./myfluka\n"
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        load_yaml_config(str(cfg), BACKENDS)
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `cd /Users/tonyf/Work/fluka-grid-search/external/FlukaQueueSub && python -m pytest tests/test_dpm_cli.py -q`
Expected: FAIL — `error: unrecognized arguments: --dpm` (or AttributeError on `use_dpm`).

- [ ] **Step 3: Add `-D/--dpm` to each backend subparser**

In `$Q/launch_jobs.py`, inside the `for name, backend in BACKENDS.items():` loop, after the `-c/--custom-exe` argument, add:
```python
        sub.add_argument("-D", "--dpm", action="store_true", dest="use_dpm",
                         help="Usa l'eseguibile DPMJET/RQMD (rfluka -d); "
                              "mutuamente esclusivo con --custom-exe")
```

- [ ] **Step 4: Validate mutual exclusivity + pass into JobInfo**

In `$Q/launch_jobs.py` `_execute_jobs`, replace:
```python
    if args.custom_exe is not None and not os.path.isfile(args.custom_exe):
        logging.error("Custom exe non trovato: %s", args.custom_exe)
        sys.exit(1)
```
with:
```python
    if getattr(args, "use_dpm", False) and args.custom_exe is not None:
        logging.error("--dpm e --custom-exe sono mutuamente esclusivi: usane uno solo.")
        sys.exit(1)
    if args.custom_exe is not None and not os.path.isfile(args.custom_exe):
        logging.error("Custom exe non trovato: %s", args.custom_exe)
        sys.exit(1)
```
And change the JobInfo construction line:
```python
        job_info = JobInfo(new_input, i, fluka_path, args.custom_exe)
```
to:
```python
        job_info = JobInfo(new_input, i, fluka_path, args.custom_exe,
                           use_dpm=getattr(args, "use_dpm", False))
```

- [ ] **Step 5: Add a DPM row to the summary table**

In `$Q/launch_jobs.py`, in `common_rows`, after the `-c` Custom exe row, add:
```python
        ["-D", f"{C['M']}DPM{C['RE']}",        f"{C['M']}{getattr(args, 'use_dpm', False)}{C['RE']}"],
```

- [ ] **Step 6: YAML config support + ME check**

In `$Q/core/config.py` `load_yaml_config`, after the `--custom-exe` line in the temp parser, add:
```python
    parser.add_argument("--dpm", dest="use_dpm", action="store_true", default=False)
```
Then, after `defaults.update(data)` and before `return Namespace(**defaults)`, add:
```python
    if defaults.get("use_dpm") and defaults.get("custom_exe"):
        raise ValueError(
            "use_dpm e custom_exe sono mutuamente esclusivi: usane uno solo."
        )
```

- [ ] **Step 7: Run the test, verify it passes**

Run: `cd /Users/tonyf/Work/fluka-grid-search/external/FlukaQueueSub && python -m pytest tests/test_dpm_cli.py -q`
Expected: PASS (4 passed).

- [ ] **Step 8: Run the whole FlukaQueueSub suite**

Run: `cd /Users/tonyf/Work/fluka-grid-search/external/FlukaQueueSub && python -m pytest -q`
Expected: PASS (Task 1 + Task 2 tests green).

- [ ] **Step 9: Commit**

```bash
cd /Users/tonyf/Work/fluka-grid-search/external/FlukaQueueSub
git add launch_jobs.py core/config.py
git commit -m "feat: --dpm CLI flag + use_dpm YAML key (mutually exclusive with custom exe)"
```

---

# PHASE B — fluka-grid-search

> CWD for Phase B: `/Users/tonyf/Work/fluka-grid-search` (call it `$G`).

## Task 3: validate mutual-exclusivity + forward `use_dpm` through the adapter

**Files:**
- Modify: `$G/grid_search/config.py` (`validate_config`)
- Modify: `$G/grid_search/backends/queue_adapter.py` (both `JobInfo(...)` builds)
- Test: `$G/tests/test_config.py`, `$G/tests/test_queue_adapter.py` (local-only)

**Interfaces:**
- Consumes: `JobInfo(..., use_dpm=...)` from Task 1.
- Produces: `validate_config` allows `use_dpm` alone, raises on `use_dpm` + `custom_executable`; `queue_adapter.submit_run` forwards `config.fluka.use_dpm` into `JobInfo`.

- [ ] **Step 1: Write the failing tests**

In `$G/tests/test_config.py`, replace `test_use_dpm_rejected` with:
```python
def test_use_dpm_alone_passes(tmp_path):
    cfg = load_config(_base_raw(tmp_path, backend="ts", use_dpm=True))
    with patch("grid_search.config.subprocess.run") as mock_run:
        mock_run.return_value.stdout = "/fluka/bin\n"
        mock_run.return_value.returncode = 0
        validate_config(cfg)  # rfluka_path set in _base_raw, so this must not raise


def test_use_dpm_plus_custom_exe_rejected(tmp_path):
    raw = _base_raw(tmp_path, backend="ts", use_dpm=True)
    raw["fluka"]["custom_executable"] = "/custom/fluka"
    cfg = load_config(raw)
    with pytest.raises(ValueError, match="mutually exclusive"):
        validate_config(cfg)
```

In `$G/tests/test_queue_adapter.py`, change the `_config` helper's `fluka`
SimpleNamespace to carry `use_dpm` (so existing calls keep working):
```python
    fluka = SimpleNamespace(custom_executable=None, use_dpm=False)
```
and add:
```python
def test_submit_run_ts_dpm_passes_d_flag(tmp_path):
    run_dir = tmp_path / "c1" / "run_0001"
    run_dir.mkdir(parents=True)
    (run_dir / "simulation_0001.inp").write_text("RANDOMIZ 1. 1.\n")
    cfg = _config("ts")
    cfg.fluka.use_dpm = True
    result = queue_adapter.submit_run(
        backend_name="ts", config=cfg, run_dir=run_dir,
        inp_filename="simulation_0001.inp", iteration=1,
        fluka_bin="/fake/fluka/bin", dry_run=True,
    )
    assert "-d" in result.split()
    assert "-e" not in result.split()
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `cd /Users/tonyf/Work/fluka-grid-search && python -m pytest tests/test_config.py tests/test_queue_adapter.py -q`
Expected: FAIL — `validate_config` still raises on `use_dpm` (config test) and `submit_run` doesn't pass `-d` (adapter test).

- [ ] **Step 3: Replace the rejection with mutual-exclusivity in `validate_config`**

In `$G/grid_search/config.py`, replace:
```python
    if config.fluka.use_dpm:
        raise ValueError(
            "fluka.use_dpm is no longer supported: submission is delegated to "
            "FlukaQueueSub, whose backends do not emit 'rfluka -d'. Add DPM support "
            "to FlukaQueueSub if you need it, then remove this check."
        )
```
with:
```python
    if config.fluka.use_dpm and config.fluka.custom_executable:
        raise ValueError(
            "fluka.use_dpm and fluka.custom_executable are mutually exclusive; "
            "set only one."
        )
```

- [ ] **Step 4: Forward `use_dpm` in `queue_adapter.submit_run`**

In `$G/grid_search/backends/queue_adapter.py`, both `JobInfo(...)` constructions
(the ts branch and the cluster branch) currently end with
`custom_exe=config.fluka.custom_executable,`. Add a line after it in each:
```python
            use_dpm=config.fluka.use_dpm,
```
So each reads:
```python
        job_info = JobInfo(
            input_file=...,
            iteration=iteration,
            fluka_path=fluka_bin,
            custom_exe=config.fluka.custom_executable,
            use_dpm=config.fluka.use_dpm,
        )
```
(keep the existing `input_file` value in each branch — absolute resolved path for
ts, `inp_filename` for cluster).

- [ ] **Step 5: Run the tests, verify they pass**

Run: `cd /Users/tonyf/Work/fluka-grid-search && python -m pytest tests/test_config.py tests/test_queue_adapter.py -q`
Expected: PASS.

- [ ] **Step 6: Run the whole grid-search suite**

Run: `cd /Users/tonyf/Work/fluka-grid-search && python -m pytest -q`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
cd /Users/tonyf/Work/fluka-grid-search
git add grid_search/config.py grid_search/backends/queue_adapter.py
git commit -m "feat: re-enable use_dpm (mutually exclusive with custom exe); forward to FlukaQueueSub"
```

---

## Task 4: docs — example config + README

**Files:**
- Modify: `$G/examples/config.yaml`
- Modify: `$G/README.md`

**Interfaces:** none (documentation).

- [ ] **Step 1: Document `use_dpm` in the example config**

In `$G/examples/config.yaml`, replace the line:
```yaml
  # use_dpm: not supported — submission is delegated to FlukaQueueSub
```
with:
```yaml
  use_dpm: false            # true → launch with rfluka -d (DPMJET/RQMD); mutually exclusive with custom_executable
```

- [ ] **Step 2: Update the README limitation note**

In `$G/README.md`, in the "Backends" section, replace:
```markdown
**Limitation:** `fluka.use_dpm` is currently rejected — the FlukaQueueSub backends do
not emit `rfluka -d`. Add DPM support to FlukaQueueSub to restore it.
```
with:
```markdown
**DPM:** set `fluka.use_dpm: true` to launch with the DPMJET/RQMD executable
(`rfluka -d`). It is mutually exclusive with `fluka.custom_executable` (`rfluka -e`).
```

- [ ] **Step 3: Commit**

```bash
cd /Users/tonyf/Work/fluka-grid-search
git add examples/config.yaml README.md
git commit -m "docs: document fluka.use_dpm (rfluka -d) option"
```

---

## Task 5: finalize — push FlukaQueueSub, bump submodule pointer, push grid-search

**Files:**
- Modify: `$G` submodule gitlink `external/FlukaQueueSub`

**Interfaces:** none.

- [ ] **Step 1: Push FlukaQueueSub**

```bash
cd /Users/tonyf/Work/fluka-grid-search/external/FlukaQueueSub
git push origin HEAD:main
```
Expected: the Task 1 + Task 2 commits land on origin/main.

- [ ] **Step 2: Bump the submodule pointer in grid-search and push**

```bash
cd /Users/tonyf/Work/fluka-grid-search
git add external/FlukaQueueSub
git commit -m "chore: bump FlukaQueueSub submodule (DPM -d support)"
git push origin main
```

- [ ] **Step 3: Final verification (both suites green, install-free)**

```bash
cd /Users/tonyf/Work/fluka-grid-search/external/FlukaQueueSub && python -m pytest -q
cd /Users/tonyf/Work/fluka-grid-search && python -m pytest -q
```
Expected: both suites PASS.

---

## Done

- `rfluka -d` (DPM) is selectable in both projects via `use_dpm`, forwarded
  grid-search → queue_adapter → JobInfo → backend.
- `-d` and `-e` are mutually exclusive, validated in FlukaQueueSub (CLI + YAML)
  and grid-search (`validate_config`).
- Docs/examples updated; both test suites green; submodule pointer bumped.
