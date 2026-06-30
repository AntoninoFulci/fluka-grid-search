# DPM launch option (`rfluka -d`) — Design

**Date:** 2026-06-24
**Status:** Approved (design)
**Scope:** FlukaQueueSub (submission) + fluka-grid-search (config passthrough)

## Summary

Add support for launching FLUKA runs with the DPMJET/RQMD executable via
`rfluka -d` (the `flukadpm` executable). This option must be **mutually exclusive**
with the custom-executable option (`rfluka -e <exe>`), and must be configurable
both in FlukaQueueSub (which builds the actual `rfluka` command) and in
fluka-grid-search (whose config is consumed by FlukaQueueSub through the
queue adapter).

Background (FLUKA docs): `rfluka` uses the standard `fluka` executable by default;
`-d` requests `flukadpm` (DPMJET/RQMD); `-e ./myfluka` requests a custom compiled
executable. `-d` and `-e` are alternatives — at most one may be used.

## Approach

**Boolean flag `use_dpm` threaded down to the `rfluka` command** (chosen over an
`executable: standard|dpm|custom` enum to stay minimal and reuse the `use_dpm`
field grid-search already has). Mutual exclusivity with the custom executable is
enforced by validation in both projects and by command-build order in the
backends.

## FlukaQueueSub changes

### `backends/base.py` — `JobInfo`
Add a field:
```python
@dataclass
class JobInfo:
    input_file: str
    iteration: int
    fluka_path: str
    custom_exe: str | None
    use_dpm: bool = False
```

### Backends (`ts.py`, `slurm.py`, `lsf.py`, `htcondor.py`)
Each builds `rfluka -M 1`. Add the `-d` branch, mutually exclusive with `-e`:
```python
# command-list backends (ts.py):
fluka_parts = ["rfluka", "-M", "1"]
if job_info.use_dpm:
    fluka_parts.append("-d")
elif job_info.custom_exe is not None:
    fluka_parts.extend(["-e", job_info.custom_exe])
fluka_parts.append(job_info.input_file)

# string-command backends (slurm/lsf/htcondor):
fluka_cmd = f"{job_info.fluka_path}/rfluka -M 1"
if job_info.use_dpm:
    fluka_cmd += " -d"
elif job_info.custom_exe is not None:
    fluka_cmd += f" -e {job_info.custom_exe}"
```
`if/elif` makes "dpm wins" deterministic; cross-field validation (below) prevents
both being set in the first place.

### CLI `launch_jobs.py`
- New argument on each backend subparser: `-D, --dpm` (`action="store_true"`,
  `dest="use_dpm"`). **Not `-d`** — `-d` is already `--output-dir`.
  Help: "Use the DPMJET/RQMD executable (rfluka -d); mutually exclusive with --custom-exe".
- Validation in `_execute_jobs`: if `args.use_dpm and args.custom_exe is not None`
  → log an error and `sys.exit(1)`.
- `JobInfo(new_input, i, fluka_path, args.custom_exe, use_dpm=args.use_dpm)`.
- Summary table: add a "DPM" row showing `args.use_dpm`.

### `core/config.py` (YAML config mode)
Add to the temporary parser so the YAML key is recognised:
```python
parser.add_argument("--dpm", dest="use_dpm", action="store_true", default=False)
```
YAML usage: `use_dpm: true`. Apply the same mutual-exclusivity check (dpm +
custom_exe) after merging, raising `ValueError`.

## fluka-grid-search changes

### `grid_search/config.py` — `validate_config`
Replace the current outright rejection of `use_dpm` with mutual-exclusivity:
```python
if config.fluka.use_dpm and config.fluka.custom_executable:
    raise ValueError(
        "fluka.use_dpm and fluka.custom_executable are mutually exclusive; set only one."
    )
```
(`FlukaConfig.use_dpm` and `custom_executable` already exist.)

### `grid_search/backends/queue_adapter.py`
Pass the flag into every `JobInfo` (ts and cluster paths):
```python
job_info = JobInfo(
    input_file=...,
    iteration=iteration,
    fluka_path=fluka_bin,
    custom_exe=config.fluka.custom_executable,
    use_dpm=config.fluka.use_dpm,
)
```

### Config / examples / README
- `examples/config.yaml`: document `fluka.use_dpm: true` (mutually exclusive with
  `custom_executable`), replacing the "not supported" comment.
- README: drop the "use_dpm is rejected" limitation note; document that DPM runs
  via `rfluka -d` and is mutually exclusive with a custom executable.

## Data flow

```
grid-search config (fluka.use_dpm) ─► queue_adapter.submit_run
        └─► JobInfo(use_dpm=…) ─► FlukaQueueSub backend ─► rfluka -M 1 -d <input>

FlukaQueueSub direct use: launch_jobs --dpm / yaml use_dpm:true
        └─► JobInfo(use_dpm=…) ─► same backend path
```

## Error handling

- Both projects reject `use_dpm` + custom executable set together, with a clear
  message, before any submission.
- No `flukadpm` path is required: `-d` tells `rfluka` to use the bundled
  `flukadpm` in the FLUKA bin dir.

## Testing

FlukaQueueSub:
- Each backend emits `-d` when `use_dpm=True`, emits `-e <exe>` when only
  `custom_exe` is set, and neither when both are unset.
- `launch_jobs` / `core.config` reject `use_dpm` + `custom_exe` together.

fluka-grid-search:
- `validate_config` passes with `use_dpm=True` alone; raises when `use_dpm` +
  `custom_executable` are both set.
- `queue_adapter.submit_run` forwards `use_dpm` into `JobInfo` (assert via a
  dpm config → the built command/JobInfo carries `-d` / `use_dpm=True`).

## Out of scope

- FlukaQueueSub's own standalone duplicate-seed abort behaviour (unchanged).
- The `-d`→`--output-dir` short option in launch_jobs (kept; DPM uses `-D/--dpm`).
