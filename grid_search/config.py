from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class FlukaConfig:
    input: Path
    custom_executable: Optional[str]
    rfluka_path: Optional[str]


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
