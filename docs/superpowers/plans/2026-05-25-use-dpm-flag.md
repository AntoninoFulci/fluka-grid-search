# use_dpm Flag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `use_dpm: true/false` YAML config option that appends `-d` to the `rfluka` command, with validation that it's mutually exclusive with `custom_executable`.

**Architecture:** One new boolean field on `FlukaConfig`; `load_config()` reads it with a `False` default; `validate_config()` raises `ValueError` if both `use_dpm` and `custom_executable` are set; `_submit_combo()` appends `-d` instead of `-e` when the flag is true. Fully backward-compatible — configs without `use_dpm` behave identically to today.

**Tech Stack:** Python 3, dataclasses, PyYAML, pytest

---

## File Map

| File | Change |
|------|--------|
| `grid_search/config.py` | Add `use_dpm: bool = False` to `FlukaConfig`; read it in `load_config()`; add mutual-exclusivity check in `validate_config()` |
| `run_grid.py` | Update `_submit_combo()` to emit `-d`; update `_print_summary()` to display DPM mode when active |
| `examples/config.yaml` | Add `use_dpm: false` with inline comment |
| `tests/test_config.py` | Four new tests: default value, explicit true, conflict raises, no-conflict passes |
| `tests/test_run_grid.py` | Two new tests: `-d` present when `use_dpm=True`, absent when `use_dpm=False` |

---

## Task 1: Add `use_dpm` to `FlukaConfig` and `load_config()`

**Files:**
- Modify: `grid_search/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the two failing tests**

Append to `tests/test_config.py`:

```python
def test_load_config_use_dpm_default():
    cfg = load_config(RAW)
    assert cfg.fluka.use_dpm is False


def test_load_config_use_dpm_true():
    raw = {**RAW, "fluka": {**RAW["fluka"], "use_dpm": True}}
    cfg = load_config(raw)
    assert cfg.fluka.use_dpm is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py::test_load_config_use_dpm_default tests/test_config.py::test_load_config_use_dpm_true -v
```

Expected: FAIL — `FlukaConfig` has no attribute `use_dpm`.

- [ ] **Step 3: Add the field to `FlukaConfig`**

In `grid_search/config.py`, update the `FlukaConfig` dataclass (replace the existing definition):

```python
@dataclass
class FlukaConfig:
    input: Path
    custom_executable: Optional[str] = None
    rfluka_path: Optional[str] = None
    primaries: Optional[int] = None
    use_dpm: bool = False
```

- [ ] **Step 4: Read the field in `load_config()`**

In `grid_search/config.py`, update the `FlukaConfig(...)` constructor call inside `load_config()` (the block starting at line 73):

```python
        fluka=FlukaConfig(
            input=inp,
            custom_executable=raw["fluka"].get("custom_executable"),
            rfluka_path=raw["fluka"].get("rfluka_path"),
            primaries=raw["fluka"].get("primaries"),
            use_dpm=bool(raw["fluka"].get("use_dpm", False)),
        ),
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_config.py::test_load_config_use_dpm_default tests/test_config.py::test_load_config_use_dpm_true -v
```

Expected: PASS both.

- [ ] **Step 6: Run the full config test suite to confirm no regressions**

```bash
pytest tests/test_config.py -v
```

Expected: all existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add grid_search/config.py tests/test_config.py
git commit -m "feat: add use_dpm field to FlukaConfig"
```

---

## Task 2: Add mutual-exclusivity validation

**Files:**
- Modify: `grid_search/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the two failing tests**

Append to `tests/test_config.py` (after the existing `test_validate_config_fluka_not_found` test):

```python
def test_validate_config_dpm_and_custom_exe_raises(tmp_path):
    inp = tmp_path / "example.inp"
    inp.write_text(MINIMAL_INP)
    raw = {
        **RAW,
        "fluka": {
            **RAW["fluka"],
            "input": str(inp),
            "use_dpm": True,
            "custom_executable": "/custom/fluka",
            "rfluka_path": "/fluka/bin",
        },
    }
    cfg = load_config(raw)
    with pytest.raises(ValueError, match="mutually exclusive"):
        validate_config(cfg)


def test_validate_config_dpm_without_custom_exe_passes(tmp_path):
    inp = tmp_path / "example.inp"
    inp.write_text(MINIMAL_INP)
    raw = {
        **RAW,
        "fluka": {
            **RAW["fluka"],
            "input": str(inp),
            "use_dpm": True,
            "rfluka_path": "/fluka/bin",
        },
    }
    cfg = load_config(raw)
    validate_config(cfg)  # must not raise
```

Note: `rfluka_path` is set in both tests so `validate_config()` skips the `fluka-config` subprocess check — no mock needed.

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py::test_validate_config_dpm_and_custom_exe_raises tests/test_config.py::test_validate_config_dpm_without_custom_exe_passes -v
```

Expected: `test_validate_config_dpm_and_custom_exe_raises` FAIL (no error raised); `test_validate_config_dpm_without_custom_exe_passes` PASS.

- [ ] **Step 3: Add the check to `validate_config()`**

In `grid_search/config.py`, append to the end of `validate_config()` (after the `except` block at line 112):

```python
    if config.fluka.use_dpm and config.fluka.custom_executable:
        raise ValueError(
            "fluka.use_dpm and fluka.custom_executable are mutually exclusive. "
            "Set only one."
        )
```

The complete `validate_config()` should now read:

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
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(
                "fluka-config not found. Install FLUKA or set fluka.rfluka_path in config."
            ) from exc

    if config.fluka.use_dpm and config.fluka.custom_executable:
        raise ValueError(
            "fluka.use_dpm and fluka.custom_executable are mutually exclusive. "
            "Set only one."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py::test_validate_config_dpm_and_custom_exe_raises tests/test_config.py::test_validate_config_dpm_without_custom_exe_passes -v
```

Expected: PASS both.

- [ ] **Step 5: Run the full config test suite**

```bash
pytest tests/test_config.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add grid_search/config.py tests/test_config.py
git commit -m "feat: validate use_dpm and custom_executable are mutually exclusive"
```

---

## Task 3: Update command building, print summary, and run_grid tests

**Files:**
- Modify: `run_grid.py`
- Test: `tests/test_run_grid.py`

- [ ] **Step 1: Add a helper and write the two failing tests**

Append to `tests/test_run_grid.py`:

```python
def make_dpm_project(tmp_path):
    """Like make_project but with use_dpm=True and a single combo."""
    inp = tmp_path / "example.inp"
    inp.write_text("#define beame 0.5\n#define mat GALLIUM\nRANDOMIZ         1.0\nSTOP\n")
    cfg = {
        "fluka": {
            "input": str(inp),
            "custom_executable": None,
            "rfluka_path": "/fluka/bin",
            "use_dpm": True,
        },
        "output": {"directory": str(tmp_path / "results")},
        "grid": {"parameters": {"beame": [0.05], "mat": ["GALLIUM"]}, "runs_per_combo": 1},
        "execution": {"max_parallel": 4},
        "postprocessing": {},
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(cfg))
    return cfg_path


def test_submit_combo_dpm_flag(tmp_path):
    cfg_path = make_dpm_project(tmp_path)
    submitted = []

    def fake_run(cmd, **_kwargs):
        r = MagicMock()
        r.stdout = str(len(submitted)) + "\n"
        r.returncode = 0
        submitted.append(cmd)
        return r

    with patch("builtins.input", return_value="yes"), \
         patch("subprocess.run", side_effect=fake_run):
        run_main([str(cfg_path)])

    # TaskSpoolerBackend wraps each command as ["ts", <actual cmd...>]
    # rfluka calls are: ["ts", "/fluka/bin/rfluka", "-M", "1", ...]
    rfluka_cmds = [c for c in submitted if c[0] == "ts" and len(c) > 1 and c[1].endswith("rfluka")]
    assert len(rfluka_cmds) == 1
    assert "-d" in rfluka_cmds[0]
    assert "-e" not in rfluka_cmds[0]


def test_submit_combo_no_dpm_flag(tmp_path):
    cfg_path = make_project(tmp_path)  # use_dpm absent → defaults to False
    submitted = []

    def fake_run(cmd, **_kwargs):
        r = MagicMock()
        r.stdout = str(len(submitted)) + "\n"
        r.returncode = 0
        submitted.append(cmd)
        return r

    with patch("builtins.input", return_value="yes"), \
         patch("subprocess.run", side_effect=fake_run):
        run_main([str(cfg_path)])

    rfluka_cmds = [c for c in submitted if c[0] == "ts" and len(c) > 1 and c[1].endswith("rfluka")]
    assert all("-d" not in cmd for cmd in rfluka_cmds)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_run_grid.py::test_submit_combo_dpm_flag tests/test_run_grid.py::test_submit_combo_no_dpm_flag -v
```

Expected: `test_submit_combo_dpm_flag` FAIL (`-d` absent from command); `test_submit_combo_no_dpm_flag` PASS.

- [ ] **Step 3: Update `_submit_combo()` in `run_grid.py`**

Replace lines 88–91 (the `cmd` build block inside `_submit_combo`):

```python
        cmd = [str(rfluka_bin / "rfluka"), "-M", "1"]
        if config.fluka.custom_executable:
            cmd += ["-e", config.fluka.custom_executable]
        cmd.append(str(inp_path.resolve()))
```

With:

```python
        cmd = [str(rfluka_bin / "rfluka"), "-M", "1"]
        if config.fluka.use_dpm:
            cmd += ["-d"]
        elif config.fluka.custom_executable:
            cmd += ["-e", config.fluka.custom_executable]
        cmd.append(str(inp_path.resolve()))
```

- [ ] **Step 4: Update `_print_summary()` in `run_grid.py`**

Find the `custom_executable` row block (lines 42–43):

```python
    if config.fluka.custom_executable:
        rows.append([f"{C}Custom exe{RE}", f"{M}{config.fluka.custom_executable}{RE}"])
```

Replace with:

```python
    if config.fluka.use_dpm:
        rows.append([f"{C}DPM mode{RE}", f"{M}enabled (flukadpm){RE}"])
    if config.fluka.custom_executable:
        rows.append([f"{C}Custom exe{RE}", f"{M}{config.fluka.custom_executable}{RE}"])
```

- [ ] **Step 5: Run the new tests to verify they pass**

```bash
pytest tests/test_run_grid.py::test_submit_combo_dpm_flag tests/test_run_grid.py::test_submit_combo_no_dpm_flag -v
```

Expected: PASS both.

- [ ] **Step 6: Run the full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add run_grid.py tests/test_run_grid.py
git commit -m "feat: emit -d flag for rfluka when use_dpm is enabled"
```

---

## Task 4: Update example config

**Files:**
- Modify: `examples/config.yaml`

- [ ] **Step 1: Add the `use_dpm` field with comment**

Replace the `fluka` section of `examples/config.yaml` with:

```yaml
fluka:
  input: simulation.inp  # place your FLUKA .inp file next to this config
  custom_executable: null
  rfluka_path: null
  primaries: 10000
  use_dpm: false  # set true to use flukadpm (DPMJET/RQMD); mutually exclusive with custom_executable
```

- [ ] **Step 2: Commit**

```bash
git add examples/config.yaml
git commit -m "docs: add use_dpm field to example config"
```
