from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re
import subprocess
import yaml


@dataclass
class FlukaConfig:
    input: Path
    custom_executable: Optional[str] = None
    rfluka_path: Optional[str] = None
    primaries: Optional[int] = None
    use_dpm: bool = False


@dataclass
class GridConfig:
    parameters: dict[str, list]
    runs_per_combo: int


@dataclass
class ExecutionConfig:
    max_parallel: int
    backend: str = "ts"          # ts | slurm | lsf | condor
    queue: Optional[str] = None  # partition (slurm) / queue (lsf) / universe (condor)
    mem: str = "1500"
    time: str = "1-00:00:00"     # slurm/lsf time limit D-HH:MM:SS
    ntasks: int = 1
    nodes: int = 1
    gres: str = "disk:1G"        # slurm only
    ncpu: int = 1                # condor only
    disk: int = 100000           # condor request_disk (kB)
    condor_max_runtime: int = 86400  # condor +MaxRuntime (seconds)


@dataclass
class Config:
    fluka: FlukaConfig
    output_dir: Path
    grid: GridConfig
    execution: ExecutionConfig


def load_config(source: dict | Path) -> Config:
    if isinstance(source, Path):
        config_dir = source.parent
        with open(source) as f:
            raw = yaml.safe_load(f)
    else:
        config_dir = None
        raw = source

    inp = Path(raw["fluka"]["input"])
    if config_dir is not None and not inp.is_absolute():
        inp = config_dir / inp

    return Config(
        fluka=FlukaConfig(
            input=inp,
            custom_executable=raw["fluka"].get("custom_executable"),
            rfluka_path=raw["fluka"].get("rfluka_path"),
            primaries=raw["fluka"].get("primaries"),
            use_dpm=bool(raw["fluka"].get("use_dpm", False)),
        ),
        output_dir=Path(raw["output"]["directory"]),
        grid=GridConfig(
            parameters=raw["grid"]["parameters"],
            runs_per_combo=raw["grid"]["runs_per_combo"],
        ),
        execution=ExecutionConfig(
            max_parallel=raw["execution"]["max_parallel"],
            backend=raw["execution"].get("backend", "ts"),
            queue=raw["execution"].get("queue"),
            mem=str(raw["execution"].get("mem", "1500")),
            time=raw["execution"].get("time", "1-00:00:00"),
            ntasks=int(raw["execution"].get("ntasks", 1)),
            nodes=int(raw["execution"].get("nodes", 1)),
            gres=raw["execution"].get("gres", "disk:1G"),
            ncpu=int(raw["execution"].get("ncpu", 1)),
            disk=int(raw["execution"].get("disk", 100000)),
            condor_max_runtime=int(raw["execution"].get("condor_max_runtime", 86400)),
        ),
    )


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

    valid_backends = {"ts", "slurm", "lsf", "condor"}
    if config.execution.backend not in valid_backends:
        raise ValueError(
            f"Unknown execution.backend {config.execution.backend!r}. "
            f"Valid: {sorted(valid_backends)}"
        )

    if config.fluka.use_dpm and config.fluka.custom_executable:
        raise ValueError(
            "fluka.use_dpm and fluka.custom_executable are mutually exclusive; "
            "set only one."
        )
