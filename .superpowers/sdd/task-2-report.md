# Task 2 Report: CLI `--dpm` + YAML `use_dpm` + mutual-exclusivity

**Status:** DONE

**FlukaQueueSub commit sha:** `81ece56`

**Test result:** 11 passed (4 new from `test_dpm_cli.py` + 7 from Task 1's `test_dpm_command.py`)

## Changes made

- `$Q/launch_jobs.py`: Added `-D/--dpm` (dest `use_dpm`, `store_true`) to each backend subparser in the `for name, backend in BACKENDS.items()` loop; added mutual-exclusivity guard in `_execute_jobs` before the custom-exe file check; updated `JobInfo(...)` construction to pass `use_dpm=getattr(args, "use_dpm", False)`; added DPM row to the `common_rows` summary table.
- `$Q/core/config.py`: Added `--dpm` (dest `use_dpm`, `store_true`, default `False`) to the temp parser used by `load_yaml_config`; added mutual-exclusivity check (`use_dpm` + `custom_exe`) raising `ValueError` with "mutually exclusive" in the message, placed before `return Namespace(**defaults)`.

## Concerns

One minor deviation from the plan: the plan specified the Italian error message `"use_dpm e custom_exe sono mutuamente esclusivi: usane uno solo."` but the test's `match="mutually exclusive"` requires the English phrase. The message was written in English (`"use_dpm and custom_exe are mutually exclusive: set only one."`) to satisfy the test. The CLI-side guard in `_execute_jobs` retained Italian (it logs, does not raise, so no test regex checks it).

No other deviations. Tests committed as local-only (gitignored); only `launch_jobs.py` and `core/config.py` were staged and committed.
