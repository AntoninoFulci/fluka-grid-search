# FLUKA Grid Search Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a resumable Python framework that runs FLUKA parameter grid searches locally via task-spooler, with automatic post-processing after each parameter combination completes.

**Architecture:** The orchestrator (`run_grid.py`) generates all parameter combinations, creates working directories with patched `.inp` files, submits N `rfluka` jobs per combo to `ts`, then submits a sentinel job that waits for the N runs to finish and drives post-processing. State is persisted in `state.json` for resumability.

**Tech Stack:** Python 3.11+, PyYAML, pytest, task-spooler (`ts`), FLUKA (`rfluka`, `usbsuw`, `usbrea`, etc.)

---

## File Map

| File | Responsibility |
|------|---------------|
| `run_grid.py` | CLI entry point — arg parsing, orchestration loop |
| `sentinel.py` | Standalone script submitted as ts job; waits for run IDs, runs post-processing |
| `grid_search/__init__.py` | Empty |
| `grid_search/config.py` | Dataclasses + `load_config()` + `validate_config()` |
| `grid_search/grid.py` | `generate_combinations()` + `combo_name()` |
| `grid_search/workspace.py` | `create_run_workspace()`, `patch_inp()`, `generate_seed()` |
| `grid_search/state.py` | `StateManager` — read/write `state.json` |
| `grid_search/postprocess.py` | `run_postprocessing()` — drives FLUKA tools via stdin |
| `grid_search/backends/__init__.py` | Empty |
| `grid_search/backends/base.py` | `ExecutionBackend` ABC |
| `grid_search/backends/task_spooler.py` | `TaskSpoolerBackend` |
| `tests/conftest.py` | Shared pytest fixtures |
| `tests/test_config.py` | Config loading + validation tests |
| `tests/test_grid.py` | Combination generation tests |
| `tests/test_workspace.py` | Directory creation + `.inp` patching tests |
| `tests/test_state.py` | StateManager tests |
| `tests/test_postprocess.py` | Post-processing stdin protocol tests |
| `tests/test_task_spooler.py` | TaskSpoolerBackend tests |
| `tests/test_sentinel.py` | Sentinel integration tests |
| `tests/test_run_grid.py` | CLI integration tests |
| `pyproject.toml` | Project metadata + deps |
| `config.yaml` | Example config file |

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `grid_search/__init__.py`
- Create: `grid_search/backends/__init__.py`
- Create: `tests/__init__.py`
- Create: `config.yaml`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "fluka-grid-search"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create directory structure and empty `__init__.py` files**

```bash
mkdir -p grid_search/backends tests
touch grid_search/__init__.py grid_search/backends/__init__.py tests/__init__.py
```

- [ ] **Step 3: Create `config.yaml`**

```yaml
fluka:
  input: 2026-01-23_Frascati_V1.inp
  custom_executable: null
  rfluka_path: null

output:
  directory: results/

grid:
  parameters:
    beame: [0.05, 0.1, 0.5]
    mat: [GALLIUM, TUNGSTEN]
  runs_per_combo: 5

execution:
  max_parallel: 4

postprocessing:
  ".21":
    executable: usbsuw
  ".22":
    executable: usbrea
```

- [ ] **Step 4: Install dev dependencies**

```bash
pip install -e ".[dev]"
```

Expected: installs pyyaml and pytest, no errors.

- [ ] **Step 5: Verify pytest runs with no tests**

```bash
pytest
```

Expected: `no tests ran` or `0 passed`.

- [ ] **Step 6: Commit**

```bash
git init
git add pyproject.toml grid_search/ tests/ config.yaml
git commit -m "chore: project scaffold"
```

---

## Task 2: Config dataclasses + YAML loading

**Files:**
- Create: `grid_search/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_config.py`:

```python
from pathlib import Path
import pytest
from grid_search.config import load_config, Config, FlukaConfig, GridConfig, ExecutionConfig


RAW = {
    "fluka": {
        "input": "example.inp",
        "custom_executable": None,
        "rfluka_path": None,
    },
    "output": {"directory": "results/"},
    "grid": {
        "parameters": {"beame": [0.05, 0.5], "mat": ["GALLIUM"]},
        "runs_per_combo": 3,
    },
    "execution": {"max_parallel": 4},
    "postprocessing": {".21": {"executable": "usbsuw"}},
}


def test_load_config_from_dict():
    cfg = load_config(RAW)
    assert isinstance(cfg, Config)
    assert cfg.fluka.input == Path("example.inp")
    assert cfg.fluka.custom_executable is None
    assert cfg.fluka.rfluka_path is None
    assert cfg.output_dir == Path("results/")
    assert cfg.grid.parameters == {"beame": [0.05, 0.5], "mat": ["GALLIUM"]}
    assert cfg.grid.runs_per_combo == 3
    assert cfg.execution.max_parallel == 4
    assert cfg.postprocessing == {".21": "usbsuw"}


def test_load_config_from_file(tmp_path):
    import yaml
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(RAW))
    cfg = load_config(cfg_file)
    assert cfg.grid.runs_per_combo == 3
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 3: Implement `grid_search/config.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class FlukaConfig:
    input: Path
    custom_executable: Optional[str]
    rfluka_path: Optional[str]


@dataclass
class GridConfig:
    parameters: dict[str, list]
    runs_per_combo: int


@dataclass
class ExecutionConfig:
    max_parallel: int


@dataclass
class Config:
    fluka: FlukaConfig
    output_dir: Path
    grid: GridConfig
    execution: ExecutionConfig
    postprocessing: dict[str, str]  # extension -> executable name


def load_config(source: dict | Path) -> Config:
    if isinstance(source, Path):
        with open(source) as f:
            raw = yaml.safe_load(f)
    else:
        raw = source

    return Config(
        fluka=FlukaConfig(
            input=Path(raw["fluka"]["input"]),
            custom_executable=raw["fluka"].get("custom_executable"),
            rfluka_path=raw["fluka"].get("rfluka_path"),
        ),
        output_dir=Path(raw["output"]["directory"]),
        grid=GridConfig(
            parameters=raw["grid"]["parameters"],
            runs_per_combo=raw["grid"]["runs_per_combo"],
        ),
        execution=ExecutionConfig(
            max_parallel=raw["execution"]["max_parallel"],
        ),
        postprocessing={
            ext: v["executable"]
            for ext, v in raw.get("postprocessing", {}).items()
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add grid_search/config.py tests/test_config.py
git commit -m "feat: config dataclasses and YAML loading"
```

---

## Task 3: Config validation

**Files:**
- Modify: `grid_search/config.py` — add `validate_config()`
- Modify: `tests/test_config.py` — add validation tests

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config.py`:

```python
import subprocess
from unittest.mock import patch
from grid_search.config import validate_config


MINIMAL_INP = """\
#define beame 0.5
#define mat GALLIUM
RANDOMIZ         1.0
START         10000.
STOP
"""


def test_validate_config_passes(tmp_path):
    inp = tmp_path / "example.inp"
    inp.write_text(MINIMAL_INP)
    raw = {**RAW, "fluka": {**RAW["fluka"], "input": str(inp)}}
    cfg = load_config(raw)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "/usr/local/fluka/bin\n"
        mock_run.return_value.returncode = 0
        validate_config(cfg)  # should not raise


def test_validate_config_missing_define(tmp_path):
    inp = tmp_path / "example.inp"
    inp.write_text("#define mat GALLIUM\nSTOP\n")  # missing beame
    raw = {**RAW, "fluka": {**RAW["fluka"], "input": str(inp)}}
    cfg = load_config(raw)
    with pytest.raises(ValueError, match="beame"):
        validate_config(cfg)


def test_validate_config_fluka_not_found(tmp_path):
    inp = tmp_path / "example.inp"
    inp.write_text(MINIMAL_INP)
    raw = {**RAW, "fluka": {**RAW["fluka"], "input": str(inp)}}
    cfg = load_config(raw)
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError
        with pytest.raises(RuntimeError, match="fluka-config"):
            validate_config(cfg)
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_config.py -v -k validate
```

Expected: `AttributeError` or `ImportError`.

- [ ] **Step 3: Add `validate_config()` to `grid_search/config.py`**

Add these imports at the top of `grid_search/config.py`:

```python
import re
import subprocess
```

Then add the function at the bottom of `grid_search/config.py`:

```python
def validate_config(config: Config) -> None:
    inp_text = config.fluka.input.read_text()
    for param in config.grid.parameters:
        if not re.search(rf"^#define\s+{re.escape(param)}\s", inp_text, re.MULTILINE):
            raise ValueError(
                f"Parameter '{param}' not found as '#define {param}' in {config.fluka.input}"
            )

    if config.fluka.rfluka_path is None:
        try:
            subprocess.run(
                ["fluka-config", "--bin"],
                capture_output=True, text=True, check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise RuntimeError(
                "fluka-config not found. Install FLUKA or set fluka.rfluka_path in config."
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add grid_search/config.py tests/test_config.py
git commit -m "feat: config validation for #define params and rfluka"
```

---

## Task 4: Grid combination generation

**Files:**
- Create: `grid_search/grid.py`
- Create: `tests/test_grid.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_grid.py`:

```python
from grid_search.grid import generate_combinations, combo_name


def test_generate_combinations_count():
    params = {"beame": [0.05, 0.1], "mat": ["GALLIUM", "TUNGSTEN"]}
    combos = generate_combinations(params)
    assert len(combos) == 4


def test_generate_combinations_single_param():
    params = {"beame": [0.05, 0.1, 0.5]}
    combos = generate_combinations(params)
    assert len(combos) == 3
    assert all("beame" in c for c in combos)


def test_generate_combinations_values():
    params = {"beame": [0.05], "mat": ["GALLIUM"]}
    combos = generate_combinations(params)
    assert combos == [{"beame": 0.05, "mat": "GALLIUM"}]


def test_combo_name_basic():
    assert combo_name({"beame": 0.05, "mat": "GALLIUM"}) == "beame0.05_matGALLIUM"


def test_combo_name_integer_value():
    assert combo_name({"beame": 1}) == "beame1"


def test_combo_name_preserves_order():
    name = combo_name({"z": 1, "a": 2})
    assert name == "z1_a2"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_grid.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `grid_search/grid.py`**

```python
from itertools import product


def generate_combinations(parameters: dict[str, list]) -> list[dict]:
    keys = list(parameters.keys())
    values = list(parameters.values())
    return [dict(zip(keys, combo)) for combo in product(*values)]


def combo_name(params: dict) -> str:
    return "_".join(f"{k}{v}" for k, v in params.items())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_grid.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add grid_search/grid.py tests/test_grid.py
git commit -m "feat: parameter combination generation"
```

---

## Task 5: Workspace creation and `.inp` patching

**Files:**
- Create: `grid_search/workspace.py`
- Create: `tests/test_workspace.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_workspace.py`:

```python
from pathlib import Path
from grid_search.workspace import create_run_workspace, patch_inp, generate_seed

TEMPLATE_INP = """\
#define beame 0.5
#define mat GALLIUM
BEAM          $beame                                                  ELECTRON
ASSIGNMA        $mat    TARGET
RANDOMIZ         1.0
START         10000.
STOP
"""


def test_create_run_workspace(tmp_path):
    ws = create_run_workspace(tmp_path, "beame0.05_matGALLIUM", 1)
    assert ws == tmp_path / "beame0.05_matGALLIUM" / "run_0001"
    assert ws.is_dir()


def test_create_run_workspace_zero_padding(tmp_path):
    ws = create_run_workspace(tmp_path, "combo", 42)
    assert ws.name == "run_0042"


def test_patch_inp_replaces_defines(tmp_path):
    template = tmp_path / "template.inp"
    template.write_text(TEMPLATE_INP)
    out = tmp_path / "patched.inp"
    patch_inp(template, out, {"beame": 0.1, "mat": "TUNGSTEN"}, seed=12345678)
    text = out.read_text()
    assert "#define beame 0.1\n" in text
    assert "#define mat TUNGSTEN\n" in text
    assert "#define beame 0.5" not in text
    assert "#define mat GALLIUM" not in text


def test_patch_inp_replaces_seed(tmp_path):
    template = tmp_path / "template.inp"
    template.write_text(TEMPLATE_INP)
    out = tmp_path / "patched.inp"
    patch_inp(template, out, {"beame": 0.5, "mat": "GALLIUM"}, seed=99999999)
    text = out.read_text()
    assert "RANDOMIZ" in text
    assert "99999999" in text
    assert "RANDOMIZ         1.0" not in text


def test_patch_inp_preserves_other_lines(tmp_path):
    template = tmp_path / "template.inp"
    template.write_text(TEMPLATE_INP)
    out = tmp_path / "patched.inp"
    patch_inp(template, out, {"beame": 0.5, "mat": "GALLIUM"}, seed=1)
    text = out.read_text()
    assert "START         10000." in text
    assert "STOP" in text


def test_generate_seed_range():
    for _ in range(100):
        s = generate_seed()
        assert 1 <= s <= int(9e7)
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_workspace.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `grid_search/workspace.py`**

```python
from __future__ import annotations
import random
import re
from pathlib import Path


def create_run_workspace(output_dir: Path, combo: str, run_idx: int) -> Path:
    run_dir = output_dir / combo / f"run_{run_idx:04d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def patch_inp(template: Path, output: Path, params: dict, seed: int) -> None:
    lines = template.read_text().splitlines(keepends=True)
    result = []
    for line in lines:
        patched = line
        for name, value in params.items():
            patched = re.sub(
                rf"^(#define\s+{re.escape(name)}\s+)\S+",
                rf"\g<1>{value}",
                patched,
            )
        if re.match(r"^RANDOMIZ\s", patched):
            patched = f"RANDOMIZ          1.{seed:>10n}\n"
        result.append(patched)
    output.write_text("".join(result))


def generate_seed() -> int:
    return random.randint(1, int(9e7))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_workspace.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add grid_search/workspace.py tests/test_workspace.py
git commit -m "feat: workspace creation and .inp patching"
```

---

## Task 6: State management

**Files:**
- Create: `grid_search/state.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_state.py`:

```python
import json
from pathlib import Path
from grid_search.state import StateManager


def test_init_combo(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.init_combo("beame0.05_matGALLIUM", {"beame": 0.05, "mat": "GALLIUM"}, n_runs=3)
    assert sm.get_combo_status("beame0.05_matGALLIUM") == "pending"
    runs = sm.data["beame0.05_matGALLIUM"]["runs"]
    assert list(runs.keys()) == ["run_0001", "run_0002", "run_0003"]
    assert all(r["status"] == "pending" for r in runs.values())


def test_save_and_load(tmp_path):
    path = tmp_path / "state.json"
    sm = StateManager(path)
    sm.init_combo("combo1", {"x": 1}, n_runs=2)
    sm.save()
    sm2 = StateManager(path)
    sm2.load()
    assert sm2.get_combo_status("combo1") == "pending"


def test_set_run_submitted(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.init_combo("combo1", {}, n_runs=2)
    sm.set_run_submitted("combo1", "run_0001", "42")
    run = sm.data["combo1"]["runs"]["run_0001"]
    assert run["ts_job_id"] == "42"
    assert run["status"] == "submitted"


def test_set_run_done(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.init_combo("combo1", {}, n_runs=1)
    sm.set_run_submitted("combo1", "run_0001", "7")
    sm.set_run_done("combo1", "run_0001", exit_code=0)
    assert sm.data["combo1"]["runs"]["run_0001"]["exit_code"] == 0
    assert sm.data["combo1"]["runs"]["run_0001"]["status"] == "done"


def test_set_combo_status(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.init_combo("combo1", {}, n_runs=1)
    sm.set_combo_status("combo1", "done")
    assert sm.get_combo_status("combo1") == "done"


def test_get_pending_combos(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.init_combo("combo1", {}, n_runs=1)
    sm.init_combo("combo2", {}, n_runs=1)
    sm.set_combo_status("combo2", "done")
    assert sm.get_pending_combos() == ["combo1"]


def test_load_missing_file(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.load()  # should not raise; starts with empty state
    assert sm.data == {}
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_state.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `grid_search/state.py`**

```python
from __future__ import annotations
import json
from pathlib import Path


class StateManager:
    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        self.data: dict = {}

    def load(self) -> None:
        if self.state_file.exists():
            self.data = json.loads(self.state_file.read_text())

    def save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.data, indent=2))

    def init_combo(self, combo: str, params: dict, n_runs: int) -> None:
        self.data[combo] = {
            "status": "pending",
            "parameters": params,
            "runs": {
                f"run_{i:04d}": {"status": "pending"}
                for i in range(1, n_runs + 1)
            },
        }

    def get_combo_status(self, combo: str) -> str:
        return self.data.get(combo, {}).get("status", "pending")

    def set_run_submitted(self, combo: str, run: str, ts_job_id: str) -> None:
        self.data[combo]["runs"][run]["ts_job_id"] = ts_job_id
        self.data[combo]["runs"][run]["status"] = "submitted"

    def set_run_done(self, combo: str, run: str, exit_code: int) -> None:
        self.data[combo]["runs"][run]["exit_code"] = exit_code
        self.data[combo]["runs"][run]["status"] = "done" if exit_code == 0 else "failed"

    def set_sentinel(self, combo: str, ts_job_id: str) -> None:
        self.data[combo]["sentinel_ts_job_id"] = ts_job_id

    def set_combo_status(self, combo: str, status: str) -> None:
        self.data[combo]["status"] = status

    def get_pending_combos(self) -> list[str]:
        return [c for c, v in self.data.items() if v["status"] == "pending"]

    def get_in_progress_combos(self) -> list[str]:
        return [
            c for c, v in self.data.items()
            if v["status"] in ("submitted", "running", "postprocessing")
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_state.py -v
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add grid_search/state.py tests/test_state.py
git commit -m "feat: state manager for resumable grid search"
```

---

## Task 7: ExecutionBackend + TaskSpoolerBackend

**Files:**
- Create: `grid_search/backends/base.py`
- Create: `grid_search/backends/task_spooler.py`
- Create: `tests/test_task_spooler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_task_spooler.py`:

```python
from pathlib import Path
from unittest.mock import patch, MagicMock
from grid_search.backends.task_spooler import TaskSpoolerBackend


def test_submit_returns_job_id(tmp_path):
    backend = TaskSpoolerBackend()
    mock_result = MagicMock()
    mock_result.stdout = "5\n"
    mock_result.returncode = 0
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        job_id = backend.submit(["rfluka", "-M", "1", "sim.inp"], tmp_path)
    assert job_id == "5"
    call_args = mock_run.call_args
    assert call_args[0][0] == ["ts", "rfluka", "-M", "1", "sim.inp"]
    assert call_args[1]["cwd"] == tmp_path


def test_submit_raises_on_failure(tmp_path):
    import subprocess, pytest
    backend = TaskSpoolerBackend()
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "ts")):
        with pytest.raises(subprocess.CalledProcessError):
            backend.submit(["rfluka", "-M", "1", "sim.inp"], tmp_path)


def test_wait_calls_ts_w():
    backend = TaskSpoolerBackend()
    with patch("subprocess.run") as mock_run:
        backend.wait("7")
    mock_run.assert_called_once_with(["ts", "-w", "7"], check=True)


def test_get_exit_code_parses_e_level():
    backend = TaskSpoolerBackend()
    ts_info = "ID: 5\nState: finished\nE-Level: 0\nTimes: 1.2/0.1/0.1\n"
    mock_result = MagicMock()
    mock_result.stdout = ts_info
    with patch("subprocess.run", return_value=mock_result):
        code = backend.get_exit_code("5")
    assert code == 0


def test_get_exit_code_nonzero():
    backend = TaskSpoolerBackend()
    ts_info = "ID: 6\nState: finished\nE-Level: 1\n"
    mock_result = MagicMock()
    mock_result.stdout = ts_info
    with patch("subprocess.run", return_value=mock_result):
        code = backend.get_exit_code("6")
    assert code == 1


def test_set_max_parallel():
    backend = TaskSpoolerBackend()
    with patch("subprocess.run") as mock_run:
        backend.set_max_parallel(4)
    mock_run.assert_called_once_with(["ts", "-S", "4"], check=True)
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_task_spooler.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `grid_search/backends/base.py`**

```python
from abc import ABC, abstractmethod
from pathlib import Path


class ExecutionBackend(ABC):
    @abstractmethod
    def submit(self, command: list[str], working_dir: Path) -> str:
        """Submit a job. Returns backend-specific job ID string."""

    @abstractmethod
    def wait(self, job_id: str) -> None:
        """Block until job completes."""

    @abstractmethod
    def get_exit_code(self, job_id: str) -> int:
        """Return exit code of a completed job."""

    @abstractmethod
    def set_max_parallel(self, n: int) -> None:
        """Set maximum number of simultaneously running jobs."""
```

- [ ] **Step 4: Create `grid_search/backends/task_spooler.py`**

```python
from __future__ import annotations
import subprocess
from pathlib import Path
from .base import ExecutionBackend


class TaskSpoolerBackend(ExecutionBackend):
    def submit(self, command: list[str], working_dir: Path) -> str:
        result = subprocess.run(
            ["ts"] + command,
            capture_output=True, text=True, check=True, cwd=working_dir,
        )
        return result.stdout.strip()

    def wait(self, job_id: str) -> None:
        subprocess.run(["ts", "-w", job_id], check=True)

    def get_exit_code(self, job_id: str) -> int:
        result = subprocess.run(
            ["ts", "-i", job_id], capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("E-Level:"):
                return int(line.split(":", 1)[1].strip())
        return -1

    def set_max_parallel(self, n: int) -> None:
        subprocess.run(["ts", "-S", str(n)], check=True)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_task_spooler.py -v
```

Expected: `6 passed`.

- [ ] **Step 6: Commit**

```bash
git add grid_search/backends/ tests/test_task_spooler.py
git commit -m "feat: ExecutionBackend ABC and TaskSpoolerBackend"
```

---

## Task 8: Post-processing runner

**Files:**
- Create: `grid_search/postprocess.py`
- Create: `tests/test_postprocess.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_postprocess.py`:

```python
from pathlib import Path
from unittest.mock import patch, MagicMock
from grid_search.postprocess import run_postprocessing


def test_run_postprocessing_stdin_format(tmp_path):
    combo_dir = tmp_path / "beame0.05_matGALLIUM"
    run1 = combo_dir / "run_0001"
    run2 = combo_dir / "run_0002"
    run1.mkdir(parents=True)
    run2.mkdir(parents=True)
    (run1 / "sim001.21").write_text("")
    (run2 / "sim002.21").write_text("")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_postprocessing(combo_dir, {".21": "usbsuw"}, [run1, run2])

    call_kwargs = mock_run.call_args
    assert call_kwargs[0][0] == ["usbsuw"]
    stdin_input = call_kwargs[1]["input"]
    assert str(run1 / "sim001.21") in stdin_input
    assert str(run2 / "sim002.21") in stdin_input
    assert stdin_input.endswith("\n\n")


def test_run_postprocessing_creates_postproc_dir(tmp_path):
    combo_dir = tmp_path / "combo"
    run1 = combo_dir / "run_0001"
    run1.mkdir(parents=True)
    (run1 / "out.21").write_text("")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        run_postprocessing(combo_dir, {".21": "usbsuw"}, [run1])

    assert (combo_dir / "postproc").is_dir()


def test_run_postprocessing_skips_missing_extension(tmp_path):
    combo_dir = tmp_path / "combo"
    run1 = combo_dir / "run_0001"
    run1.mkdir(parents=True)
    # no .21 files

    with patch("subprocess.run") as mock_run:
        run_postprocessing(combo_dir, {".21": "usbsuw"}, [run1])

    mock_run.assert_not_called()


def test_run_postprocessing_saves_log(tmp_path):
    combo_dir = tmp_path / "combo"
    run1 = combo_dir / "run_0001"
    run1.mkdir(parents=True)
    (run1 / "out.21").write_text("")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="merged ok", stderr="")
        run_postprocessing(combo_dir, {".21": "usbsuw"}, [run1])

    log = combo_dir / "postproc" / "usbsuw.log"
    assert log.exists()
    assert "merged ok" in log.read_text()
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_postprocess.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `grid_search/postprocess.py`**

```python
from __future__ import annotations
import subprocess
from pathlib import Path


def run_postprocessing(
    combo_dir: Path,
    postprocessing: dict[str, str],
    successful_run_dirs: list[Path],
) -> None:
    postproc_dir = combo_dir / "postproc"
    postproc_dir.mkdir(parents=True, exist_ok=True)

    for extension, executable in postprocessing.items():
        files = [
            f
            for run_dir in successful_run_dirs
            for f in sorted(run_dir.glob(f"*{extension}"))
        ]
        if not files:
            continue

        stdin_input = "\n".join(str(f) for f in files) + "\n\n"
        result = subprocess.run(
            [executable],
            input=stdin_input,
            text=True,
            capture_output=True,
            cwd=postproc_dir,
        )
        log_path = postproc_dir / f"{executable}.log"
        log_path.write_text(result.stdout + result.stderr)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_postprocess.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add grid_search/postprocess.py tests/test_postprocess.py
git commit -m "feat: postprocessing runner with FLUKA stdin protocol"
```

---

## Task 9: Sentinel script

**Files:**
- Create: `sentinel.py`
- Create: `tests/test_sentinel.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_sentinel.py`:

```python
import importlib.util
import json
import sys
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock


def run_sentinel(args: list[str]):
    spec = importlib.util.spec_from_file_location(
        "sentinel", Path(__file__).parent.parent / "sentinel.py"
    )
    mod = importlib.util.module_from_spec(spec)
    with patch.object(sys, "argv", ["sentinel.py"] + args):
        spec.loader.exec_module(mod)
    return mod


def make_state(tmp_path, combo, job_ids):
    state = {
        combo: {
            "status": "submitted",
            "parameters": {},
            "runs": {
                f"run_{i+1:04d}": {"ts_job_id": jid, "status": "submitted"}
                for i, jid in enumerate(job_ids)
            },
        }
    }
    (tmp_path / "state.json").write_text(json.dumps(state))


def make_config(tmp_path):
    inp = tmp_path / "example.inp"
    inp.write_text("#define beame 0.5\nRANDOMIZ         1.0\nSTOP\n")
    cfg = {
        "fluka": {"input": str(inp), "custom_executable": None, "rfluka_path": "/fluka/bin"},
        "output": {"directory": str(tmp_path)},
        "grid": {"parameters": {"beame": [0.5]}, "runs_per_combo": 1},
        "execution": {"max_parallel": 2},
        "postprocessing": {},
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(cfg))
    return cfg_path


def test_sentinel_waits_for_all_job_ids(tmp_path):
    combo = "beame0.5"
    job_ids = ["10", "11", "12"]
    make_state(tmp_path, combo, job_ids)
    cfg_path = make_config(tmp_path)

    waited = []

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["ts", "-w"]:
            waited.append(cmd[2])
        r = MagicMock()
        r.stdout = "E-Level: 0\n"
        r.stderr = ""
        r.returncode = 0
        return r

    with patch("subprocess.run", side_effect=fake_run):
        run_sentinel([str(cfg_path), str(tmp_path), combo] + job_ids)

    assert sorted(waited) == sorted(job_ids)


def test_sentinel_marks_combo_done(tmp_path):
    combo = "beame0.5"
    make_state(tmp_path, combo, ["5"])
    cfg_path = make_config(tmp_path)

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.stdout = "E-Level: 0\n"
        r.stderr = ""
        r.returncode = 0
        return r

    with patch("subprocess.run", side_effect=fake_run):
        run_sentinel([str(cfg_path), str(tmp_path), combo, "5"])

    state = json.loads((tmp_path / "state.json").read_text())
    assert state[combo]["status"] == "done"


def test_sentinel_marks_combo_partial_on_failure(tmp_path):
    combo = "beame0.5"
    make_state(tmp_path, combo, ["5", "6"])
    cfg_path = make_config(tmp_path)

    codes = {"5": 0, "6": 1}

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        if cmd[:2] == ["ts", "-i"]:
            r.stdout = f"E-Level: {codes[cmd[2]]}\n"
        else:
            r.stdout = ""
        r.stderr = ""
        r.returncode = 0
        return r

    with patch("subprocess.run", side_effect=fake_run):
        run_sentinel([str(cfg_path), str(tmp_path), combo, "5", "6"])

    state = json.loads((tmp_path / "state.json").read_text())
    assert state[combo]["status"] == "partial"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_sentinel.py -v
```

Expected: failures (sentinel.py doesn't exist).

- [ ] **Step 3: Implement `sentinel.py`**

```python
#!/usr/bin/env python3
"""Submitted as a ts job after N runs for a combo. Waits for runs, then post-processes."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

from grid_search.backends.task_spooler import TaskSpoolerBackend
from grid_search.config import load_config
from grid_search.postprocess import run_postprocessing
from grid_search.state import StateManager


def main() -> None:
    config_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    combo = sys.argv[3]
    job_ids = sys.argv[4:]

    config = load_config(config_path)
    state = StateManager(output_dir / "state.json")
    state.load()
    backend = TaskSpoolerBackend()

    for job_id in job_ids:
        backend.wait(job_id)

    successful_run_dirs = []
    for run_name, run_info in state.data[combo]["runs"].items():
        ts_id = str(run_info["ts_job_id"])
        exit_code = backend.get_exit_code(ts_id)
        state.set_run_done(combo, run_name, exit_code)
        if exit_code == 0:
            successful_run_dirs.append(output_dir / combo / run_name)

    state.set_combo_status(combo, "postprocessing")
    state.save()

    if successful_run_dirs and config.postprocessing:
        run_postprocessing(output_dir / combo, config.postprocessing, successful_run_dirs)

    n_total = len(job_ids)
    n_ok = len(successful_run_dirs)
    final_status = "done" if n_ok == n_total else "partial"
    state.set_combo_status(combo, final_status)
    state.save()

    print(f"[sentinel] {combo}: {n_ok}/{n_total} runs succeeded → {final_status}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_sentinel.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add sentinel.py tests/test_sentinel.py
git commit -m "feat: sentinel script for post-processing after combo completes"
```

---

## Task 10: CLI — core submission loop

**Files:**
- Create: `run_grid.py`
- Create: `tests/test_run_grid.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_run_grid.py`:

```python
import importlib.util
import json
import sys
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


def make_project(tmp_path):
    inp = tmp_path / "example.inp"
    inp.write_text("#define beame 0.5\n#define mat GALLIUM\nRANDOMIZ         1.0\nSTOP\n")
    cfg = {
        "fluka": {"input": str(inp), "custom_executable": None, "rfluka_path": "/fluka/bin"},
        "output": {"directory": str(tmp_path / "results")},
        "grid": {"parameters": {"beame": [0.05, 0.1], "mat": ["GALLIUM"]}, "runs_per_combo": 2},
        "execution": {"max_parallel": 4},
        "postprocessing": {},
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(cfg))
    return cfg_path


def run_main(argv):
    spec = importlib.util.spec_from_file_location(
        "run_grid", Path(__file__).parent.parent / "run_grid.py"
    )
    mod = importlib.util.module_from_spec(spec)
    with patch.object(sys, "argv", ["run_grid.py"] + argv):
        spec.loader.exec_module(mod)
    return mod


def test_dry_run_submits_nothing(tmp_path, capsys):
    cfg_path = make_project(tmp_path)
    with patch("subprocess.run") as mock_run:
        run_main([str(cfg_path), "--dry-run"])
    for call in mock_run.call_args_list:
        assert call[0][0][0] != "ts"
    out = capsys.readouterr().out
    assert "[dry-run]" in out


def test_submits_correct_number_of_jobs(tmp_path):
    cfg_path = make_project(tmp_path)
    submitted = []

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.stdout = str(len(submitted)) + "\n"
        r.returncode = 0
        submitted.append(cmd)
        return r

    with patch("subprocess.run", side_effect=fake_run):
        run_main([str(cfg_path)])

    ts_submissions = [c for c in submitted if c[0] == "ts"]
    # 2 combos × (2 runs + 1 sentinel) = 6 ts calls + 1 ts -S call = 7
    assert len(ts_submissions) == 7


def test_state_written_after_submit(tmp_path):
    cfg_path = make_project(tmp_path)
    job_counter = [0]

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        job_counter[0] += 1
        r.stdout = str(job_counter[0]) + "\n"
        r.returncode = 0
        return r

    with patch("subprocess.run", side_effect=fake_run):
        run_main([str(cfg_path)])

    state_file = tmp_path / "results" / "state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert "beame0.05_matGALLIUM" in state
    assert "beame0.1_matGALLIUM" in state


def test_skips_done_combos(tmp_path):
    cfg_path = make_project(tmp_path)
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    state = {
        "beame0.05_matGALLIUM": {"status": "done", "parameters": {}, "runs": {}},
        "beame0.1_matGALLIUM": {"status": "pending", "parameters": {}, "runs": {}},
    }
    (results_dir / "state.json").write_text(json.dumps(state))

    submitted = []

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.stdout = str(len(submitted)) + "\n"
        r.returncode = 0
        submitted.append(cmd)
        return r

    with patch("subprocess.run", side_effect=fake_run):
        run_main([str(cfg_path)])

    ts_submissions = [c for c in submitted if c[0] == "ts" and c[1] != "-S"]
    # only 1 combo: 2 runs + 1 sentinel = 3
    assert len(ts_submissions) == 3
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_run_grid.py -v
```

Expected: `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 3: Implement `run_grid.py`**

```python
#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path

from grid_search.backends.task_spooler import TaskSpoolerBackend
from grid_search.config import load_config, validate_config
from grid_search.grid import combo_name, generate_combinations
from grid_search.state import StateManager
from grid_search.workspace import create_run_workspace, generate_seed, patch_inp


def _parse_args():
    import argparse
    p = argparse.ArgumentParser(description="FLUKA grid search launcher")
    p.add_argument("config", type=Path)
    p.add_argument("--reset", action="store_true", help="Delete output dir and start fresh")
    p.add_argument("--postprocess", action="store_true", help="Re-run post-processing only")
    p.add_argument("--combo", help="Limit --postprocess to one combo")
    p.add_argument("--dry-run", action="store_true", help="Print commands without submitting")
    return p.parse_args()


def _resolve_rfluka(config) -> Path:
    import subprocess
    if config.fluka.rfluka_path:
        return Path(config.fluka.rfluka_path)
    result = subprocess.run(
        ["fluka-config", "--bin"], capture_output=True, text=True, check=True
    )
    return Path(result.stdout.strip())


def _submit_combo(params, config, rfluka_bin, backend, state, args):
    name = combo_name(params)
    n_runs = config.grid.runs_per_combo
    state.init_combo(name, params, n_runs)
    job_ids = []

    for i in range(1, n_runs + 1):
        run_name = f"run_{i:04d}"
        run_dir = create_run_workspace(config.output_dir, name, i)
        seed = generate_seed()
        inp_path = run_dir / f"simulation_{i:04d}.inp"
        patch_inp(config.fluka.input, inp_path, params, seed)

        cmd = [str(rfluka_bin / "rfluka"), "-M", "1"]
        if config.fluka.custom_executable:
            cmd += ["-e", config.fluka.custom_executable]
        cmd.append(str(inp_path))

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
            str(Path(__file__).parent / "sentinel.py"),
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


def _do_postprocess(config, state, args):
    from grid_search.postprocess import run_postprocessing
    combos = [args.combo] if args.combo else list(state.data.keys())
    for name in combos:
        combo_data = state.data.get(name)
        if not combo_data:
            print(f"[postprocess] {name}: not found in state, skipping")
            continue
        successful_runs = [
            config.output_dir / name / run
            for run, info in combo_data["runs"].items()
            if info.get("exit_code", -1) == 0
        ]
        if not successful_runs:
            print(f"[postprocess] {name}: no successful runs, skipping")
            continue
        print(f"[postprocess] {name}: processing {len(successful_runs)} runs...")
        run_postprocessing(config.output_dir / name, config.postprocessing, successful_runs)
        state.set_combo_status(name, "done")
        state.save()


def main() -> None:
    args = _parse_args()

    if args.reset and args.postprocess:
        print("Error: --reset and --postprocess are mutually exclusive")
        sys.exit(1)

    config = load_config(args.config)
    validate_config(config)

    if args.reset:
        import shutil
        if config.output_dir.exists():
            confirm = input(f"Delete {config.output_dir} and all contents? [yes/N] ")
            if confirm.strip().lower() not in ("yes", "y"):
                print("Aborted.")
                sys.exit(0)
            shutil.rmtree(config.output_dir)
            print(f"Deleted {config.output_dir}")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    state_file = config.output_dir / "state.json"
    state = StateManager(state_file)
    if state_file.exists():
        state.load()

    if args.postprocess:
        _do_postprocess(config, state, args)
        return

    backend = TaskSpoolerBackend()
    backend.set_max_parallel(config.execution.max_parallel)
    rfluka_bin = _resolve_rfluka(config)

    for params in generate_combinations(config.grid.parameters):
        name = combo_name(params)
        status = state.get_combo_status(name)
        if status == "done":
            print(f"Skipping {name} (already done)")
            continue
        if status in ("submitted", "running", "postprocessing"):
            print(f"Skipping {name} (already in progress, sentinel running)")
            continue
        _submit_combo(params, config, rfluka_bin, backend, state, args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_run_grid.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests passing.

- [ ] **Step 6: Commit**

```bash
git add run_grid.py tests/test_run_grid.py
git commit -m "feat: CLI entry point with submission loop and resumability"
```

---

## Task 11: CLI — `--reset` and `--postprocess` flags

**Files:**
- Modify: `tests/test_run_grid.py` — add flag-specific tests

- [ ] **Step 1: Write tests for `--reset`**

Append to `tests/test_run_grid.py`:

```python
def test_reset_deletes_output_dir(tmp_path, monkeypatch):
    cfg_path = make_project(tmp_path)
    results = tmp_path / "results"
    results.mkdir()
    (results / "state.json").write_text("{}")

    monkeypatch.setattr("builtins.input", lambda _: "yes")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="1\n", returncode=0)
        run_main([str(cfg_path), "--reset"])

    state_file = results / "state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert "beame0.05_matGALLIUM" in state  # freshly submitted


def test_reset_aborts_on_no(tmp_path, monkeypatch, capsys):
    cfg_path = make_project(tmp_path)
    results = tmp_path / "results"
    results.mkdir()
    marker = results / "keep_me.txt"
    marker.write_text("important")

    monkeypatch.setattr("builtins.input", lambda _: "no")

    run_main([str(cfg_path), "--reset"])

    assert marker.exists()
    out = capsys.readouterr().out
    assert "Aborted" in out
```

- [ ] **Step 2: Write tests for `--postprocess`**

Append to `tests/test_run_grid.py`:

```python
def test_postprocess_flag_calls_run_postprocessing(tmp_path):
    cfg_path = make_project(tmp_path)
    results = tmp_path / "results"
    results.mkdir()
    combo = "beame0.05_matGALLIUM"
    run1 = results / combo / "run_0001"
    run1.mkdir(parents=True)
    state = {
        combo: {
            "status": "submitted",
            "parameters": {},
            "runs": {"run_0001": {"status": "done", "exit_code": 0}},
        }
    }
    (results / "state.json").write_text(json.dumps(state))

    with patch("grid_search.postprocess.run_postprocessing") as mock_pp:
        run_main([str(cfg_path), "--postprocess"])

    mock_pp.assert_called_once()
    call_args = mock_pp.call_args[0]
    assert call_args[0] == results / combo
    assert call_args[2] == [run1]
```

- [ ] **Step 3: Run new tests**

```bash
pytest tests/test_run_grid.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Run full suite**

```bash
pytest -v
```

Expected: all tests passing, zero failures.

- [ ] **Step 5: Final commit**

```bash
git add tests/test_run_grid.py
git commit -m "test: --reset and --postprocess flag coverage"
```

---

## Implementation notes

- **Sentinel slot consumption:** Each sentinel holds one `ts` slot while calling `ts -w`. With `runs_per_combo=5` and `max_parallel=4`, consider setting `max_parallel` to 6–8 so sentinels don't starve FLUKA jobs of slots.
- **No `os.chdir()`:** All subprocess calls use `cwd=`. The existing `FlukaQueueSub/launch_jobs_ts.py` uses `os.chdir()` which is unsafe in concurrent contexts — this framework avoids it entirely.
- **`ts -S <n>`** sets max parallel slots globally. It affects the entire `ts` daemon, not just this session's jobs.
- **`rfluka` path** is resolved once at startup and reused for all submissions.
