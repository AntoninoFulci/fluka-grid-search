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


main()
