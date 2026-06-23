from __future__ import annotations
import os
from argparse import Namespace
from pathlib import Path

# FlukaQueueSub (installed via submodule, editable)
from backends.base import JobInfo
from backends.slurm import SlurmBackend
from backends.lsf import LSFBackend
from backends.htcondor import HTCondorBackend
from backends.ts import TSBackend

BACKENDS = {
    "ts": TSBackend,
    "slurm": SlurmBackend,
    "lsf": LSFBackend,
    "condor": HTCondorBackend,
}

_DEFAULT_QUEUE = {"slurm": "production", "lsf": "normal", "condor": "vanilla"}


def _build_namespace(backend_name: str, config, dry_run: bool) -> Namespace:
    if backend_name == "ts":
        return Namespace(dry_run=dry_run)
    if backend_name not in _DEFAULT_QUEUE:
        raise ValueError(f"Unknown backend: {backend_name!r}")
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
            # NOTE: keep in sync with FlukaQueueSub HTCondorBackend.add_args defaults
            output="job_$(Cluster)_$(Process).out",
            error="job_$(Cluster)_$(Process).err",
            log="job_$(Cluster)_$(Process).log",
        )


def submit_run(
    backend_name: str,
    config,
    run_dir: Path,
    inp_filename: str,
    iteration: int,
    fluka_bin: str,
    dry_run: bool,
) -> str:
    """Submit one run via a FlukaQueueSub backend. Returns the job-id string."""
    backend = BACKENDS[backend_name]()
    ns = _build_namespace(backend_name, config, dry_run)
    backend.validate(ns)

    if backend_name == "ts":
        # TSBackend runs `ts rfluka -M 1 <input>` in the process CWD, so run it
        # from inside run_dir with an absolute input path (rfluka writes there).
        job_info = JobInfo(
            input_file=str((Path(run_dir) / inp_filename).resolve()),
            iteration=iteration,
            fluka_path=fluka_bin,
            custom_exe=config.fluka.custom_executable,
        )
        cwd = os.getcwd()
        os.chdir(run_dir)
        try:
            return backend.submit(None, job_info, ns)
        finally:
            os.chdir(cwd)

    job_info = JobInfo(
        input_file=inp_filename,
        iteration=iteration,
        fluka_path=fluka_bin,
        custom_exe=config.fluka.custom_executable,
    )
    script_path = backend.generate_script(job_info, str(Path(run_dir).resolve()), ns)
    return backend.submit(script_path, job_info, ns)
