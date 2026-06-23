#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path

from grid_search.backends import queue_adapter
from grid_search.config import load_config, validate_config
from grid_search.grid import combo_name, generate_combinations
from grid_search.workspace import create_run_workspace, patch_inp
from grid_search.seeds import scan_used_seeds, next_seed, find_duplicate_seeds


def _parse_args():
    import argparse
    p = argparse.ArgumentParser(
        description="FLUKA grid search launcher: generate input files and submit them "
                    "to the farm via FlukaQueueSub."
    )
    p.add_argument("config", type=Path)
    p.add_argument("--reset", action="store_true", help="Delete output dir and start fresh")
    p.add_argument("--dry-run", action="store_true", help="Print commands without submitting")
    p.add_argument("--check-seeds", action="store_true",
                   help="Audit the output dir for duplicate RANDOMIZ seeds and exit")
    return p.parse_args()


def _print_summary(config, args, rfluka_bin) -> None:
    from math import prod
    from colorama import Fore, Style, init as colorama_init
    from tabulate import tabulate

    colorama_init(autoreset=True)
    C, M, B, Y, G = Fore.CYAN, Fore.MAGENTA, Fore.BLUE, Fore.YELLOW, Fore.GREEN
    RE = Style.RESET_ALL

    n_combos = prod(len(v) for v in config.grid.parameters.values())
    n_jobs = n_combos * config.grid.runs_per_combo

    rows = [["Field", "Value"]]
    rows.append([f"{C}Config{RE}",      f"{M}{args.config}{RE}"])
    rows.append([f"{C}Input{RE}",       f"{M}{config.fluka.input}{RE}"])
    rows.append([f"{C}Output dir{RE}",  f"{M}{config.output_dir}{RE}"])
    rows.append([f"{C}Backend{RE}",     f"{M}{config.execution.backend}{RE}"])
    rows.append([f"{C}rfluka bin{RE}",  f"{M}{rfluka_bin}{RE}"])
    if config.fluka.custom_executable:
        rows.append([f"{C}Custom exe{RE}", f"{M}{config.fluka.custom_executable}{RE}"])
    if config.fluka.primaries:
        rows.append([f"{C}Primaries{RE}",  f"{M}{config.fluka.primaries}{RE}"])
    rows.append(["", ""])
    for param, values in config.grid.parameters.items():
        rows.append([f"{B}  {param}{RE}", f"{Y}{', '.join(str(v) for v in values)}{RE}"])
    rows.append(["", ""])
    rows.append([f"{C}Runs / combo{RE}", f"{M}{config.grid.runs_per_combo}{RE}"])
    rows.append([f"{C}Max parallel{RE}", f"{M}{config.execution.max_parallel}{RE}"])
    rows.append([f"{G}Total combos{RE}", f"{G}{n_combos}{RE}"])
    rows.append([f"{G}Total jobs{RE}",   f"{G}{n_jobs}{RE}"])
    rows.append([f"{Y}Dry run{RE}",      f"{Y}{args.dry_run}{RE}"])

    print(tabulate(rows, headers="firstrow", tablefmt="simple_outline"))

    if not args.dry_run:
        confirm = input("Proceed with launching jobs? (yes/no): ")
        if confirm.strip().lower() not in ("yes", "y"):
            print("Aborted.")
            sys.exit(0)


def _resolve_rfluka(config) -> Path:
    import subprocess
    if config.fluka.rfluka_path:
        return Path(config.fluka.rfluka_path)
    result = subprocess.run(
        ["fluka-config", "--bin"], capture_output=True, text=True, check=True
    )
    return Path(result.stdout.strip())


def _set_ts_slots(max_parallel: int) -> None:
    """Set the task-spooler slot count (local concurrency) before submitting."""
    import subprocess
    subprocess.run(["ts", "-S", str(max_parallel)], check=False)


def _submit_combo(params, config, rfluka_bin, args) -> None:
    name = combo_name(params)
    n_runs = config.grid.runs_per_combo

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

    # Phase 3: submit every run via FlukaQueueSub (submit-only; no monitoring here)
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
        print(f"[{config.execution.backend}] {name}/{run_name}: {job_id}")

    print(
        f"Submitted {name}: {n_runs} runs via {config.execution.backend}. "
        f"Monitoring, post-processing and analysis are handled by FlukaQueueSub / "
        f"FlukaIsotopeAnalysis."
    )


def main() -> None:
    args = _parse_args()

    config = load_config(args.config)
    validate_config(config)

    if args.check_seeds:
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

    rfluka_bin = _resolve_rfluka(config)
    _print_summary(config, args, rfluka_bin)

    if config.execution.backend == "ts" and not args.dry_run:
        _set_ts_slots(config.execution.max_parallel)

    for params in generate_combinations(config.grid.parameters):
        _submit_combo(params, config, rfluka_bin, args)


if __name__ == "__main__":
    main()
