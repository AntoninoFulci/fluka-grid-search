# Design: `use_dpm` Flag for FLUKA Grid Search

**Date:** 2026-05-25  
**Status:** Approved

---

## Overview

Add support for the `rfluka -d` option, which selects the alternative `flukadpm` executable for simulations requiring DPMJET and RQMD physics models. This is surfaced as a `use_dpm: true/false` boolean in the `fluka` section of the YAML config. The flag is mutually exclusive with `custom_executable` and that constraint is enforced at validation time.

---

## Motivation

`rfluka` offers two ways to override the default FLUKA executable:

- `-e <path>` — use a user-supplied executable (existing `custom_executable` field)
- `-d` — use the built-in `flukadpm` binary (DPMJET/RQMD support)

These two options conflict at the `rfluka` level: both change which executable is run, so specifying both is meaningless. The project must expose `-d` cleanly and prevent users from accidentally combining it with `custom_executable`.

---

## Data Model

`FlukaConfig` in `grid_search/config.py` gains one new field:

```python
@dataclass
class FlukaConfig:
    input: Path
    custom_executable: Optional[str] = None
    rfluka_path: Optional[str] = None
    primaries: Optional[int] = None
    use_dpm: bool = False          # new
```

Default is `False`, preserving full backward compatibility — existing configs without `use_dpm` continue to work unchanged.

---

## Config Loading

`load_config()` reads the new field with a safe default:

```python
FlukaConfig(
    ...
    use_dpm=bool(raw["fluka"].get("use_dpm", False)),
)
```

No other changes to parsing logic.

---

## Validation

`validate_config()` enforces mutual exclusivity after the existing checks:

```python
if config.fluka.use_dpm and config.fluka.custom_executable:
    raise ValueError(
        "fluka.use_dpm and fluka.custom_executable are mutually exclusive. "
        "Set only one."
    )
```

Raises `ValueError` with a clear message pointing at both field names. This follows the existing validation style (same function, same exception type).

---

## Command Building

In `run_grid.py`, `_submit_combo()` currently appends `-e` when `custom_executable` is set. The updated logic:

```python
cmd = [str(rfluka_bin / "rfluka"), "-M", "1"]
if config.fluka.use_dpm:
    cmd += ["-d"]
elif config.fluka.custom_executable:
    cmd += ["-e", config.fluka.custom_executable]
cmd.append(str(inp_path.resolve()))
```

The `elif` makes the mutual exclusivity structurally visible even after validation has passed.

---

## Summary Display

`_print_summary()` gains a row for DPM mode, shown only when active — matching the existing pattern for `custom_executable`:

```python
if config.fluka.use_dpm:
    rows.append([f"{C}DPM mode{RE}", f"{M}enabled (flukadpm){RE}"])
```

---

## Config File (`examples/config.yaml`)

The example config is updated with the new field and an inline comment:

```yaml
fluka:
  input: simulation.inp
  custom_executable: null
  rfluka_path: null
  primaries: 10000
  use_dpm: false   # set true to use flukadpm (DPMJET/RQMD); mutually exclusive with custom_executable
```

---

## Tests

New tests to add in `tests/test_config.py`:

| Test | Asserts |
|------|---------|
| `test_load_config_use_dpm_default` | `use_dpm` is `False` when absent from config |
| `test_load_config_use_dpm_true` | `use_dpm` is `True` when `use_dpm: true` in YAML |
| `test_validate_config_dpm_and_custom_exe_raises` | `validate_config()` raises `ValueError` when both are set |
| `test_validate_config_dpm_without_custom_exe_passes` | No error when `use_dpm=True` and `custom_executable=None` |

New test in `tests/test_run_grid.py`:

| Test | Asserts |
|------|---------|
| `test_submit_combo_dpm_flag` | Command contains `-d` when `use_dpm=True` |
| `test_submit_combo_no_dpm_flag` | Command does not contain `-d` when `use_dpm=False` |

---

## Constraints

- `use_dpm: true` + `custom_executable: <path>` → `validate_config()` raises `ValueError`
- `use_dpm: false` (default) → behavior identical to current
- No changes to backend, state, workspace, or postprocessing logic
