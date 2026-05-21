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


@dataclass
class GridConfig:
    parameters: dict[str, list]
    runs_per_combo: int


@dataclass
class ExecutionConfig:
    max_parallel: int


@dataclass
class Config:
    fluka: FlukaConfig
    output_dir: Path
    grid: GridConfig
    execution: ExecutionConfig
    postprocessing: dict[str, str]  # extension -> executable name


def load_config(source: dict | Path) -> Config:
    if isinstance(source, Path):
        with open(source) as f:
            raw = yaml.safe_load(f)
    else:
        raw = source

    return Config(
        fluka=FlukaConfig(
            input=Path(raw["fluka"]["input"]),
            custom_executable=raw["fluka"].get("custom_executable"),
            rfluka_path=raw["fluka"].get("rfluka_path"),
        ),
        output_dir=Path(raw["output"]["directory"]),
        grid=GridConfig(
            parameters=raw["grid"]["parameters"],
            runs_per_combo=raw["grid"]["runs_per_combo"],
        ),
        execution=ExecutionConfig(
            max_parallel=raw["execution"]["max_parallel"],
        ),
        postprocessing={
            ext: v["executable"]
            for ext, v in raw.get("postprocessing", {}).items()
        },
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
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise RuntimeError(
                "fluka-config not found. Install FLUKA or set fluka.rfluka_path in config."
            )
