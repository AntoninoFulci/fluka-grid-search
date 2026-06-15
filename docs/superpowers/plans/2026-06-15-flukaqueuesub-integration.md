# FlukaQueueSub Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SLURM/LSF/HTCondor submission to `fluka-grid-search` by depending on `FlukaQueueSub` (git submodule), and replace grid-search's naive seed generation with FlukaQueueSub's robust unique-seed primitives — keeping the existing Task Spooler path and sentinel unchanged.

**Architecture:** FlukaQueueSub is added as a git submodule under `external/FlukaQueueSub`, packaged with a minimal `pyproject.toml`, and installed editable so its top-level `core` and `backends` packages import cleanly. Grid-search gains a layout-aware seed module (`grid_search/seeds.py`) wrapping FlukaQueueSub `parse_randomiz` + `allocate_seed`, and a cluster adapter (`grid_search/backends/queue_adapter.py`) driving FlukaQueueSub's SLURM/LSF/Condor backend objects. `run_grid.py` branches on `execution.backend`: `ts` keeps the existing submit + sentinel flow; cluster backends submit-only with manual post-processing.

**Tech Stack:** Python ≥3.11, pytest, git submodules, setuptools editable install, FlukaQueueSub (`core`, `backends`), task-spooler / SLURM / LSF / HTCondor clients.

**Reference spec:** `docs/superpowers/specs/2026-06-15-flukaqueuesub-integration-design.md`

**Note on `tests/` and `pyproject.toml`:** the grid-search `.gitignore` currently ignores `tests/` and `pyproject.toml`. Test files in this plan are still created and run locally; they simply are not committed (matching the repo's existing convention). Do **not** un-ignore them as part of this work unless the user asks.

---

## File Structure

**FlukaQueueSub (submodule) — created:**
- `pyproject.toml` — minimal packaging so `core` + `backends` install as importable top-level packages.

**fluka-grid-search — created:**
- `external/FlukaQueueSub` — git submodule.
- `grid_search/seeds.py` — layout-aware seed scanning/allocation over `output_dir/<combo>/run_*/*.inp`.
- `grid_search/backends/queue_adapter.py` — builds `Namespace` + `JobInfo`, drives FlukaQueueSub cluster backends.
- `tests/test_seeds.py`, `tests/test_queue_adapter.py` — new tests (local only, gitignored).

**fluka-grid-search — modified:**
- `grid_search/config.py` — `ExecutionConfig` gains `backend` + cluster params; `validate_config` rejects `use_dpm` + cluster.
- `run_grid.py` — `_submit_combo` restructured into prepare → audit → submit phases; branches `ts` vs cluster; uses `seeds` module.
- `check_seeds` — standalone duplicate audit entry (new `--check-seeds` flag on `run_grid.py`).

---

## Task 0: Add FlukaQueueSub submodule and package it

**Files:**
- Create: `external/FlukaQueueSub/pyproject.toml` (inside the submodule)
- Modify: `.gitmodules` (created by `git submodule add`)

- [ ] **Step 1: Determine the submodule source URL**

Run:
```bash
git -C /Users/tonyf/Work/FlukaQueueSub remote get-url origin 2>/dev/null || echo "NO_REMOTE"
```
If a URL prints, use it as `<SRC>`. If `NO_REMOTE`, use the local path `/Users/tonyf/Work/FlukaQueueSub` as `<SRC>`.

- [ ] **Step 2: Add the submodule**

Run (from the fluka-grid-search repo root, on branch `feat/flukaqueuesub-integration`):
```bash
git submodule add <SRC> external/FlukaQueueSub
git submodule update --init --recursive
```
Expected: `external/FlukaQueueSub` populated with FlukaQueueSub's tree (`core/`, `backends/`, `launch_jobs.py`, ...).

- [ ] **Step 3: Add packaging to FlukaQueueSub**

Create `external/FlukaQueueSub/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "flukaqueuesub"
version = "0.1.0"
description = "Multi-backend FLUKA job submission (SLURM/LSF/HTCondor/Task Spooler)"
requires-python = ">=3.10"
dependencies = ["pyyaml", "colorama", "tabulate", "rich"]

[tool.setuptools]
py-modules = ["launch_jobs", "collect_results", "check_seeds"]
packages = ["core", "backends"]
```
Note: `htcondor` is intentionally omitted — it is only needed for live Condor submission and is provided by the cluster environment.

- [ ] **Step 4: Install FlukaQueueSub editable**

Run:
```bash
pip install -e external/FlukaQueueSub
```
Expected: `Successfully installed flukaqueuesub-0.1.0`.

- [ ] **Step 5: Smoke-test the import**

Run:
```bash
python -c "from core.fluka import allocate_seed, parse_randomiz; from backends.slurm import SlurmBackend; print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add .gitmodules external/FlukaQueueSub
git commit -m "build: vendor FlukaQueueSub as submodule and package it"
```
Note: the `pyproject.toml` lives inside the submodule and is committed in the submodule's own repo. Commit it there too:
```bash
git -C external/FlukaQueueSub add pyproject.toml
git -C external/FlukaQueueSub commit -m "build: add minimal pyproject for packaging"
git add external/FlukaQueueSub
git commit -m "build: pin FlukaQueueSub submodule to packaged commit"
```

---

## Task 1: Seed module (`grid_search/seeds.py`)

**Files:**
- Create: `grid_search/seeds.py`
- Test: `tests/test_seeds.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_seeds.py`:
```python
from pathlib import Path

from grid_search.seeds import scan_used_seeds, next_seed, find_duplicate_seeds


def _write_inp(path: Path, seed: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"* test input\nRANDOMIZ          1.{seed:>10d}\nSTART        1000.\nSTOP\n")


def test_scan_used_seeds_reads_combo_run_tree(tmp_path):
    _write_inp(tmp_path / "beame0.1_matGALLIUM" / "run_0001" / "simulation_0001.inp", 111)
    _write_inp(tmp_path / "beame0.1_matGALLIUM" / "run_0002" / "simulation_0002.inp", 222)
    _write_inp(tmp_path / "beame0.5_matTUNGSTEN" / "run_0001" / "simulation_0001.inp", 333)
    assert scan_used_seeds(tmp_path) == {111, 222, 333}


def test_scan_used_seeds_empty_when_dir_missing(tmp_path):
    assert scan_used_seeds(tmp_path / "nope") == set()


def test_next_seed_never_returns_used(tmp_path):
    used = {1, 2, 3}
    s = next_seed(used)
    assert s not in {1, 2, 3}
    assert s in used  # allocate_seed records it


def test_find_duplicate_seeds_flags_only_shared(tmp_path):
    _write_inp(tmp_path / "c1" / "run_0001" / "a.inp", 555)
    _write_inp(tmp_path / "c2" / "run_0001" / "b.inp", 555)
    _write_inp(tmp_path / "c3" / "run_0001" / "c.inp", 777)
    dups = find_duplicate_seeds(tmp_path)
    assert set(dups.keys()) == {555}
    assert len(dups[555]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_seeds.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'grid_search.seeds'`.

- [ ] **Step 3: Write minimal implementation**

Create `grid_search/seeds.py`:
```python
from __future__ import annotations
from pathlib import Path

from core.fluka import allocate_seed, parse_randomiz


def scan_used_seeds(output_dir: Path) -> set[int]:
    """Collect RANDOMIZ seeds from every <combo>/run_*/*.inp under output_dir."""
    root = Path(output_dir)
    used: set[int] = set()
    if not root.is_dir():
        return used
    for inp in root.glob("*/run_*/*.inp"):
        seed = parse_randomiz(inp)
        if seed is not None:
            used.add(seed)
    return used


def next_seed(used: set[int]) -> int:
    """Allocate a fresh seed not in `used`; records it in `used` and returns it."""
    return allocate_seed(used)


def find_duplicate_seeds(output_dir: Path) -> dict[int, list[Path]]:
    """Return seeds shared by more than one run input under output_dir."""
    root = Path(output_dir)
    seeds: dict[int, list[Path]] = {}
    if not root.is_dir():
        return {}
    for inp in sorted(root.glob("*/run_*/*.inp")):
        seed = parse_randomiz(inp)
        if seed is not None:
            seeds.setdefault(seed, []).append(inp)
    return {s: files for s, files in seeds.items() if len(files) > 1}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_seeds.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add grid_search/seeds.py
git commit -m "feat: add layout-aware seed module over FlukaQueueSub primitives"
```

---

## Task 2: Use the seed module in `_submit_combo` (replace `generate_seed`)

**Files:**
- Modify: `run_grid.py:77-120` (`_submit_combo`)
- Test: `tests/test_run_grid.py` (extend)

This task restructures `_submit_combo` into **prepare → audit → submit** phases and replaces `workspace.generate_seed()` with unique allocation from `grid_search.seeds`. The TS submit + sentinel logic is preserved verbatim in the submit phase.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_run_grid.py`:
```python
from pathlib import Path
from unittest.mock import MagicMock
import run_grid
from grid_search.seeds import scan_used_seeds


def test_submit_combo_allocates_unique_seeds(tmp_path, monkeypatch):
    template = tmp_path / "sim.inp"
    template.write_text("#define beame 0.1\nRANDOMIZ          1.        1.\nSTART        1000.\nSTOP\n")

    class _F:
        input = template
        primaries = None
        use_dpm = False
        custom_executable = None
    class _G:
        runs_per_combo = 3
    class _Cfg:
        fluka = _F()
        grid = _G()
        output_dir = tmp_path / "out"
        execution = MagicMock(backend="ts")
    cfg = _Cfg()
    cfg.output_dir.mkdir()

    backend = MagicMock()
    backend.submit.side_effect = [f"job{i}" for i in range(10)]
    state = MagicMock()
    args = MagicMock(dry_run=False, config=tmp_path / "config.yaml")

    run_grid._submit_combo({"beame": 0.1}, cfg, Path("/fake/bin"), backend, state, args)

    seeds = scan_used_seeds(cfg.output_dir)
    assert len(seeds) == 3  # three distinct seeds, no collisions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_run_grid.py::test_submit_combo_allocates_unique_seeds -v`
Expected: FAIL — current `_submit_combo` calls `generate_seed()` (module-level random, no dedup tracking); the test asserts on `scan_used_seeds`. Fails on the unique-seed wiring or seed-count assertion.

- [ ] **Step 3: Rewrite `_submit_combo`**

Replace the import line in `run_grid.py:10`:
```python
from grid_search.workspace import create_run_workspace, patch_inp
```
(remove `generate_seed` from the import).

Add near the other imports:
```python
from grid_search.seeds import scan_used_seeds, next_seed, find_duplicate_seeds
```

Replace `_submit_combo` (`run_grid.py:77-120`) with:
```python
def _submit_combo(params, config, rfluka_bin, backend, state, args):
    name = combo_name(params)
    n_runs = config.grid.runs_per_combo
    state.init_combo(name, params, n_runs)

    # Phase 1: prepare every run (dir + patched .inp + unique seed)
    used = scan_used_seeds(config.output_dir)
    prepared = []  # (run_idx, run_name, run_dir, inp_path)
    for i in range(1, n_runs + 1):
        run_name = f"run_{i:04d}"
        run_dir = create_run_workspace(config.output_dir, name, i)
        seed = next_seed(used)
        inp_path = run_dir / f"simulation_{i:04d}.inp"
        patch_inp(config.fluka.input, inp_path, params, seed, config.fluka.primaries)
        prepared.append((i, run_name, run_dir, inp_path))

    # Phase 2: abort if any duplicate seed exists on disk
    dups = find_duplicate_seeds(config.output_dir)
    if dups:
        for seed, files in sorted(dups.items()):
            shared = ", ".join(f"{f.parent.parent.name}/{f.parent.name}" for f in files)
            print(f"[error] duplicate seed {seed} shared by: {shared}")
        sys.exit(f"[error] {name}: duplicate RANDOMIZ seeds detected, submission aborted.")

    # Phase 3: submit (TS path — submit runs + sentinel)
    job_ids = []
    for i, run_name, run_dir, inp_path in prepared:
        cmd = [str(rfluka_bin / "rfluka"), "-M", "1"]
        if config.fluka.use_dpm:
            cmd += ["-d"]
        elif config.fluka.custom_executable:
            cmd += ["-e", config.fluka.custom_executable]
        cmd.append(str(inp_path.resolve()))

        if args.dry_run:
            print(f"[dry-run] ts {' '.join(cmd)}")
        else:
            job_id = backend.submit(cmd, run_dir)
            state.set_run_submitted(name, run_name, job_id)
            job_ids.append(job_id)
            state.save()

    if not args.dry_run:
        sentinel_cmd = [
            sys.executable,
            str(Path(__file__).parent / "grid_search" / "sentinel.py"),
            str(args.config.resolve()),
            str(config.output_dir.resolve()),
            name,
        ] + job_ids
        sentinel_id = backend.submit(sentinel_cmd, Path.cwd())
        state.set_sentinel(name, sentinel_id)
        state.set_combo_status(name, "submitted")
        state.save()
        print(f"Submitted {name}: {n_runs} runs + sentinel (job {sentinel_id})")
    else:
        print(f"[dry-run] sentinel for {name}")
```

(The cluster branch is added in Task 5; for now Phase 3 keeps the TS-only behaviour so this task is independently green.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_run_grid.py -v`
Expected: PASS (existing tests + the new one).

- [ ] **Step 5: Run the full suite for regressions**

Run: `pytest -q`
Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add run_grid.py
git commit -m "refactor: prepare/audit/submit phases + robust unique seeds in _submit_combo"
```

---

## Task 3: Config — backend selection, cluster params, dpm guard

**Files:**
- Modify: `grid_search/config.py:25-28` (`ExecutionConfig`), `:86-88` (loader), `:97-121` (`validate_config`)
- Test: `tests/test_config.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:
```python
import pytest
from grid_search.config import load_config, validate_config


def _base_raw(tmp_path, backend="ts", use_dpm=False):
    inp = tmp_path / "sim.inp"
    inp.write_text("#define beame 0.1\nRANDOMIZ          1.        1.\nSTART 1000.\nSTOP\n")
    return {
        "fluka": {"input": str(inp), "rfluka_path": "/fake/bin", "use_dpm": use_dpm},
        "output": {"directory": str(tmp_path / "out")},
        "grid": {"parameters": {"beame": [0.1]}, "runs_per_combo": 1},
        "execution": {"max_parallel": 4, "backend": backend, "queue": "production"},
    }


def test_execution_backend_loaded(tmp_path):
    cfg = load_config(_base_raw(tmp_path, backend="slurm"))
    assert cfg.execution.backend == "slurm"
    assert cfg.execution.queue == "production"


def test_backend_defaults_to_ts(tmp_path):
    raw = _base_raw(tmp_path)
    del raw["execution"]["backend"]
    cfg = load_config(raw)
    assert cfg.execution.backend == "ts"


def test_dpm_plus_cluster_rejected(tmp_path):
    cfg = load_config(_base_raw(tmp_path, backend="slurm", use_dpm=True))
    with pytest.raises(ValueError, match="use_dpm.*cluster"):
        validate_config(cfg)


def test_unknown_backend_rejected(tmp_path):
    cfg = load_config(_base_raw(tmp_path, backend="pbs"))
    with pytest.raises(ValueError, match="backend"):
        validate_config(cfg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ExecutionConfig` has no `backend`/`queue` fields (`TypeError` on construction).

- [ ] **Step 3: Extend `ExecutionConfig` and the loader**

Replace `ExecutionConfig` (`grid_search/config.py:25-28`) with:
```python
@dataclass
class ExecutionConfig:
    max_parallel: int
    backend: str = "ts"          # ts | slurm | lsf | condor
    queue: Optional[str] = None  # partition (slurm) / queue (lsf) / universe (condor)
    mem: str = "1500"
    time: str = "1-00:00:00"     # slurm/lsf time limit D-HH:MM:SS
    ntasks: int = 1
    nodes: int = 1
    gres: str = "disk:1G"        # slurm only
    ncpu: int = 1                # condor only
    disk: int = 100000           # condor request_disk (kB)
    condor_max_runtime: int = 86400  # condor +MaxRuntime (seconds)
```

Replace the `execution=ExecutionConfig(...)` block (`grid_search/config.py:86-88`) with:
```python
        execution=ExecutionConfig(
            max_parallel=raw["execution"]["max_parallel"],
            backend=raw["execution"].get("backend", "ts"),
            queue=raw["execution"].get("queue"),
            mem=str(raw["execution"].get("mem", "1500")),
            time=raw["execution"].get("time", "1-00:00:00"),
            ntasks=int(raw["execution"].get("ntasks", 1)),
            nodes=int(raw["execution"].get("nodes", 1)),
            gres=raw["execution"].get("gres", "disk:1G"),
            ncpu=int(raw["execution"].get("ncpu", 1)),
            disk=int(raw["execution"].get("disk", 100000)),
            condor_max_runtime=int(raw["execution"].get("condor_max_runtime", 86400)),
        ),
```

- [ ] **Step 4: Add validation rules**

Append to `validate_config` (after the existing checks, end of `grid_search/config.py`):
```python
    valid_backends = {"ts", "slurm", "lsf", "condor"}
    if config.execution.backend not in valid_backends:
        raise ValueError(
            f"Unknown execution.backend {config.execution.backend!r}. "
            f"Valid: {sorted(valid_backends)}"
        )

    if config.fluka.use_dpm and config.execution.backend != "ts":
        raise ValueError(
            "fluka.use_dpm is only supported with the 'ts' backend; the cluster "
            "backends cannot emit 'rfluka -d'. Disable use_dpm or use backend: ts."
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (all, including the four new tests).

- [ ] **Step 6: Commit**

```bash
git add grid_search/config.py
git commit -m "feat: execution.backend + cluster params + dpm/cluster guard in config"
```

---

## Task 4: Cluster adapter (`grid_search/backends/queue_adapter.py`)

**Files:**
- Create: `grid_search/backends/queue_adapter.py`
- Test: `tests/test_queue_adapter.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_queue_adapter.py`:
```python
from pathlib import Path
from types import SimpleNamespace

from grid_search.backends import queue_adapter


def _config(backend):
    execution = SimpleNamespace(
        backend=backend, queue=None, mem="2000", time="2-00:00:00",
        ntasks=1, nodes=1, gres="disk:1G", ncpu=2, disk=100000,
        condor_max_runtime=86400, max_parallel=4,
    )
    fluka = SimpleNamespace(custom_executable=None)
    return SimpleNamespace(execution=execution, fluka=fluka)


def test_build_namespace_slurm_defaults_queue():
    ns = queue_adapter._build_namespace("slurm", _config("slurm"), dry_run=True)
    assert ns.queue == "production"
    assert ns.mem == "2000"
    assert ns.gres == "disk:1G"
    assert ns.dry_run is True


def test_build_namespace_condor_defaults_universe():
    ns = queue_adapter._build_namespace("condor", _config("condor"), dry_run=True)
    assert ns.queue == "vanilla"
    assert ns.ncpu == 2
    assert ns.time == 86400


def test_submit_run_slurm_dry_run(tmp_path):
    run_dir = tmp_path / "c1" / "run_0001"
    run_dir.mkdir(parents=True)
    (run_dir / "simulation_0001.inp").write_text("RANDOMIZ 1. 1.\n")
    result = queue_adapter.submit_run(
        backend_name="slurm",
        config=_config("slurm"),
        run_dir=run_dir,
        inp_filename="simulation_0001.inp",
        iteration=1,
        fluka_bin="/fake/fluka/bin",
        dry_run=True,
    )
    assert result.startswith("[dry run] sbatch")
    # generate_script wrote the job script into the run dir
    assert (run_dir / "job_0001.sh").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_queue_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'grid_search.backends.queue_adapter'`.

- [ ] **Step 3: Write the adapter**

Create `grid_search/backends/queue_adapter.py`:
```python
from __future__ import annotations
from argparse import Namespace
from pathlib import Path

# FlukaQueueSub (installed via submodule, editable)
from backends.base import JobInfo
from backends.slurm import SlurmBackend
from backends.lsf import LSFBackend
from backends.htcondor import HTCondorBackend

CLUSTER_BACKENDS = {
    "slurm": SlurmBackend,
    "lsf": LSFBackend,
    "condor": HTCondorBackend,
}

_DEFAULT_QUEUE = {"slurm": "production", "lsf": "normal", "condor": "vanilla"}


def _build_namespace(backend_name: str, config, dry_run: bool) -> Namespace:
    ex = config.execution
    queue = ex.queue or _DEFAULT_QUEUE[backend_name]
    if backend_name == "slurm":
        return Namespace(
            dry_run=dry_run, queue=queue, mem=ex.mem, ntasks=ex.ntasks,
            nodes=ex.nodes, time=ex.time, gres=ex.gres,
        )
    if backend_name == "lsf":
        return Namespace(
            dry_run=dry_run, queue=queue, mem=ex.mem, ntasks=ex.ntasks, time=ex.time,
        )
    if backend_name == "condor":
        return Namespace(
            dry_run=dry_run, queue=queue, mem=ex.mem, ncpu=ex.ncpu, disk=ex.disk,
            time=ex.condor_max_runtime, transfer_files="yes",
            output="job_$(Cluster)_$(Process).out",
            error="job_$(Cluster)_$(Process).err",
            log="job_$(Cluster)_$(Process).log",
        )
    raise ValueError(f"Unknown cluster backend: {backend_name!r}")


def submit_run(
    backend_name: str,
    config,
    run_dir: Path,
    inp_filename: str,
    iteration: int,
    fluka_bin: str,
    dry_run: bool,
) -> str:
    """Submit one run via a FlukaQueueSub cluster backend. Returns the job-id string."""
    backend = CLUSTER_BACKENDS[backend_name]()
    ns = _build_namespace(backend_name, config, dry_run)
    backend.validate(ns)
    job_info = JobInfo(
        input_file=inp_filename,
        iteration=iteration,
        fluka_path=fluka_bin,
        custom_exe=config.fluka.custom_executable,
    )
    script_path = backend.generate_script(job_info, str(Path(run_dir).resolve()), ns)
    return backend.submit(script_path, job_info, ns)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_queue_adapter.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add grid_search/backends/queue_adapter.py
git commit -m "feat: cluster adapter driving FlukaQueueSub slurm/lsf/condor backends"
```

---

## Task 5: Branch `run_grid` on backend (ts vs cluster)

**Files:**
- Modify: `run_grid.py` — `_submit_combo` (add cluster branch), `main` (backend selection + fluka path resolution)
- Test: `tests/test_run_grid.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_run_grid.py`:
```python
from unittest.mock import MagicMock, patch
from pathlib import Path
import run_grid


def test_submit_combo_cluster_calls_adapter(tmp_path):
    template = tmp_path / "sim.inp"
    template.write_text("#define beame 0.1\nRANDOMIZ          1.        1.\nSTART 1000.\nSTOP\n")

    class _F:
        input = template
        primaries = None
        use_dpm = False
        custom_executable = None
    class _G:
        runs_per_combo = 2
    cfg = MagicMock()
    cfg.fluka = _F()
    cfg.grid = _G()
    cfg.output_dir = tmp_path / "out"
    cfg.execution = MagicMock(backend="slurm")
    cfg.output_dir.mkdir()
    state = MagicMock()
    args = MagicMock(dry_run=False, config=tmp_path / "config.yaml")

    with patch.object(run_grid.queue_adapter, "submit_run", return_value="12345") as m:
        run_grid._submit_combo({"beame": 0.1}, cfg, Path("/fake/bin"), None, state, args)

    assert m.call_count == 2  # one per run, no sentinel
    # cluster path must NOT submit a sentinel
    assert state.set_sentinel.call_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_run_grid.py::test_submit_combo_cluster_calls_adapter -v`
Expected: FAIL — `run_grid` has no `queue_adapter` reference and `_submit_combo` has no cluster branch.

- [ ] **Step 3: Add the cluster branch**

Add the import near the top of `run_grid.py`:
```python
from grid_search.backends import queue_adapter
```

In `_submit_combo`, replace **Phase 3** (the `# Phase 3: submit ...` block from Task 2) with a branch on `config.execution.backend`:
```python
    # Phase 3: submit
    if config.execution.backend == "ts":
        job_ids = []
        for i, run_name, run_dir, inp_path in prepared:
            cmd = [str(rfluka_bin / "rfluka"), "-M", "1"]
            if config.fluka.use_dpm:
                cmd += ["-d"]
            elif config.fluka.custom_executable:
                cmd += ["-e", config.fluka.custom_executable]
            cmd.append(str(inp_path.resolve()))

            if args.dry_run:
                print(f"[dry-run] ts {' '.join(cmd)}")
            else:
                job_id = backend.submit(cmd, run_dir)
                state.set_run_submitted(name, run_name, job_id)
                job_ids.append(job_id)
                state.save()

        if not args.dry_run:
            sentinel_cmd = [
                sys.executable,
                str(Path(__file__).parent / "grid_search" / "sentinel.py"),
                str(args.config.resolve()),
                str(config.output_dir.resolve()),
                name,
            ] + job_ids
            sentinel_id = backend.submit(sentinel_cmd, Path.cwd())
            state.set_sentinel(name, sentinel_id)
            state.set_combo_status(name, "submitted")
            state.save()
            print(f"Submitted {name}: {n_runs} runs + sentinel (job {sentinel_id})")
        else:
            print(f"[dry-run] sentinel for {name}")
    else:
        # Cluster backends: submit-only, no sentinel. rfluka_bin is the FLUKA bin dir.
        for i, run_name, run_dir, inp_path in prepared:
            job_id = queue_adapter.submit_run(
                backend_name=config.execution.backend,
                config=config,
                run_dir=run_dir,
                inp_filename=inp_path.name,
                iteration=i,
                fluka_bin=str(rfluka_bin),
                dry_run=args.dry_run,
            )
            if not args.dry_run:
                state.set_run_submitted(name, run_name, job_id)
                state.save()
            print(f"[{config.execution.backend}] {name}/{run_name}: {job_id}")
        if not args.dry_run:
            state.set_combo_status(name, "submitted")
            state.save()
        print(
            f"Submitted {name}: {n_runs} runs via {config.execution.backend} "
            f"(submit-only). Run `python run_grid.py <config> --postprocess` "
            f"after the jobs finish."
        )
```

- [ ] **Step 4: Update `main` to select the backend and resolve the FLUKA path**

Replace the backend setup block in `main` (`run_grid.py:194-198`) with:
```python
    backend_name = config.execution.backend
    if backend_name == "ts":
        backend = TaskSpoolerBackend()
        if not args.dry_run:
            backend.set_max_parallel(config.execution.max_parallel)
        rfluka_bin = _resolve_rfluka(config)
    else:
        backend = None
        from core.fluka import detect_fluka_path
        rfluka_bin = Path(detect_fluka_path()[0])
    _print_summary(config, args, rfluka_bin)
```
(`detect_fluka_path()` returns `(bin, folder)`; the cluster scripts use `{fluka_path}/rfluka`, so the bin dir is correct.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_run_grid.py -v`
Expected: PASS (ts and cluster branch tests).

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add run_grid.py
git commit -m "feat: branch run_grid on execution.backend (ts sentinel vs cluster submit-only)"
```

---

## Task 6: Standalone seed audit (`--check-seeds`)

**Files:**
- Modify: `run_grid.py` — `_parse_args` (add flag), `main` (handle flag)
- Test: `tests/test_run_grid.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_run_grid.py`:
```python
import sys
import pytest
import run_grid


def test_check_seeds_reports_duplicates(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    (out / "c1" / "run_0001").mkdir(parents=True)
    (out / "c2" / "run_0001").mkdir(parents=True)
    (out / "c1" / "run_0001" / "a.inp").write_text("RANDOMIZ          1.       999\n")
    (out / "c2" / "run_0001" / "b.inp").write_text("RANDOMIZ          1.       999\n")

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "fluka:\n  input: sim.inp\n  rfluka_path: /fake/bin\n"
        "output:\n  directory: %s\n"
        "grid:\n  parameters:\n    beame: [0.1]\n  runs_per_combo: 1\n"
        "execution:\n  max_parallel: 4\n" % out
    )
    (tmp_path / "sim.inp").write_text("#define beame 0.1\nRANDOMIZ 1. 1.\nSTART 1000.\nSTOP\n")

    monkeypatch.setattr(sys, "argv", ["run_grid.py", str(cfg_file), "--check-seeds"])
    with pytest.raises(SystemExit) as exc:
        run_grid.main()
    assert exc.value.code != 0
    assert "999" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_run_grid.py::test_check_seeds_reports_duplicates -v`
Expected: FAIL — `--check-seeds` is not a recognized argument.

- [ ] **Step 3: Add the flag and handler**

In `_parse_args` (`run_grid.py:13-22`), add:
```python
    p.add_argument("--check-seeds", action="store_true",
                   help="Audit the output dir for duplicate RANDOMIZ seeds and exit")
```

In `main`, after `config = load_config(args.config)` / `validate_config(config)` and before the `--reset` handling, add:
```python
    if args.check_seeds:
        from grid_search.seeds import find_duplicate_seeds
        dups = find_duplicate_seeds(config.output_dir)
        if dups:
            for seed, files in sorted(dups.items()):
                shared = ", ".join(
                    f"{f.parent.parent.name}/{f.parent.name}" for f in files
                )
                print(f"duplicate seed {seed}: {shared}")
            sys.exit(f"{len(dups)} duplicate seed(s) found in {config.output_dir}")
        print(f"No duplicate seeds in {config.output_dir}")
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_run_grid.py::test_check_seeds_reports_duplicates -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add run_grid.py
git commit -m "feat: --check-seeds standalone duplicate-seed audit"
```

---

## Task 7: Example config + README note

**Files:**
- Create: `examples/config_slurm.yaml`
- Modify: `README.md` (add a "Cluster backends" section)

- [ ] **Step 1: Add a cluster example config**

Create `examples/config_slurm.yaml`:
```yaml
fluka:
  input: my_simulation.inp
  primaries: 10000

output:
  directory: results/

grid:
  parameters:
    beame: [0.05, 0.1, 0.5]
    mat: [GALLIUM, TUNGSTEN]
  runs_per_combo: 5

execution:
  backend: slurm        # ts | slurm | lsf | condor
  max_parallel: 4       # ts only
  queue: production     # slurm partition / lsf queue / condor universe
  mem: "2000"
  time: "2-00:00:00"    # slurm/lsf
  ntasks: 1
  nodes: 1
  gres: "disk:1G"       # slurm only

postprocessing:
  ".21":
    executable: usbsuw
```

- [ ] **Step 2: Add README section**

Add to `README.md` (after the Quick Start section):
~~~markdown
## Cluster backends (SLURM / LSF / HTCondor)

Submission is delegated to the bundled [FlukaQueueSub](external/FlukaQueueSub)
submodule. Select the backend in the config:

```yaml
execution:
  backend: slurm   # ts (default) | slurm | lsf | condor
  queue: production
  mem: "2000"
  time: "2-00:00:00"
```

- **Task Spooler (`ts`)** — the default. Submits runs, then a sentinel job that
  waits for the combo to finish and runs post-processing automatically.
- **Cluster backends (`slurm`/`lsf`/`condor`)** — submit-only. After the jobs
  finish, run post-processing manually:
  ```bash
  python run_grid.py config_slurm.yaml --postprocess
  python run_grid.py config_slurm.yaml --analyze
  ```

**Seed uniqueness** is enforced across the whole grid for every backend. Audit at
any time:
```bash
python run_grid.py config.yaml --check-seeds
```

**Limitation:** `fluka.use_dpm` is supported only with the `ts` backend.
~~~

- [ ] **Step 3: Run the full suite (no regressions)**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add examples/config_slurm.yaml README.md
git commit -m "docs: cluster backend example config and README section"
```

---

## Final verification

- [ ] **Run full suite:** `pytest -q` → all pass.
- [ ] **Dry-run each backend** against a real `.inp` template:
  ```bash
  python run_grid.py examples/config.yaml --dry-run            # ts
  python run_grid.py examples/config_slurm.yaml --dry-run      # slurm
  ```
  Expected: slurm dry-run prints `[slurm] <combo>/run_NNNN: [dry run] sbatch ...` per run, no sentinel, and a "submit-only / run --postprocess after" reminder.
- [ ] **Seed audit:** `python run_grid.py examples/config.yaml --check-seeds` → "No duplicate seeds".
- [ ] **Confirm submodule pinned:** `git submodule status` shows `external/FlukaQueueSub` at the packaged commit.
