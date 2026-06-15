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
    if backend_name not in _DEFAULT_QUEUE:
        raise ValueError(f"Unknown cluster backend: {backend_name!r}")
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
