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


@dataclass
class IsotopeConfig:
    isotopes: dict[int, int]
    rnc_files: list[str]
    output: str = "isotopes.xlsx"
    volume: float = 1.0
    pivot_group_by: Optional[str] = None


@dataclass
class Config:
    fluka: FlukaConfig
    output_dir: Path
    grid: GridConfig
    execution: ExecutionConfig
    postprocessing: dict[str, str]  # extension -> executable name
    isotope_analysis: Optional[IsotopeConfig] = None


def load_config(source: dict | Path) -> Config:
    if isinstance(source, Path):
        config_dir = source.parent
        with open(source) as f:
            raw = yaml.safe_load(f)
    else:
        config_dir = None
        raw = source

    ia_raw = raw.get("isotope_analysis")
    isotope_analysis = None
    if ia_raw:
        isotope_analysis = IsotopeConfig(
            isotopes={int(k): int(v) for k, v in ia_raw["isotopes"].items()},
            rnc_files=list(ia_raw["rnc_files"]),
            output=ia_raw.get("output", "isotopes.xlsx"),
            volume=float(ia_raw.get("volume", 1.0)),
            pivot_group_by=ia_raw.get("pivot_group_by"),
        )

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
        ),
        postprocessing={
            ext: v["executable"]
            for ext, v in raw.get("postprocessing", {}).items()
        },
        isotope_analysis=isotope_analysis,
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
