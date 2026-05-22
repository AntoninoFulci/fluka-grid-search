#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path

from grid_search.backends.task_spooler import TaskSpoolerBackend
from grid_search.config import load_config, validate_config
from grid_search.grid import combo_name, generate_combinations
from grid_search.isotope_analysis import run_isotope_analysis
from grid_search.state import StateManager
from grid_search.workspace import create_run_workspace, generate_seed, patch_inp


def _parse_args():
    import argparse
    p = argparse.ArgumentParser(description="FLUKA grid search launcher")
    p.add_argument("config", type=Path)
    p.add_argument("--reset", action="store_true", help="Delete output dir and start fresh")
    p.add_argument("--postprocess", action="store_true", help="Re-run post-processing only")
    p.add_argument("--analyze", action="store_true", help="Run isotope analysis on post-processed data")
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
        patch_inp(config.fluka.input, inp_path, params, seed, config.fluka.primaries)

        cmd = [str(rfluka_bin / "rfluka"), "-M", "1"]
        if config.fluka.custom_executable:
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


def _do_analyze(config, state, args):
    if config.isotope_analysis is None:
        print("Error: no isotope_analysis section in config")
        sys.exit(1)
    run_isotope_analysis(config.output_dir, config, state, combo=args.combo)


def main() -> None:
    args = _parse_args()

    if args.reset and args.postprocess:
        print("Error: --reset and --postprocess are mutually exclusive")
        sys.exit(1)

    if args.reset and args.analyze:
        print("Error: --reset and --analyze are mutually exclusive")
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

    if args.analyze:
        _do_analyze(config, state, args)
        return

    backend = TaskSpoolerBackend()
    if not args.dry_run:
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
