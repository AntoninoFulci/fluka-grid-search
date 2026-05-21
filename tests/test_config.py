from pathlib import Path
import pytest
from grid_search.config import load_config, Config, FlukaConfig, GridConfig, ExecutionConfig


RAW = {
    "fluka": {
        "input": "example.inp",
        "custom_executable": None,
        "rfluka_path": None,
    },
    "output": {"directory": "results/"},
    "grid": {
        "parameters": {"beame": [0.05, 0.5], "mat": ["GALLIUM"]},
        "runs_per_combo": 3,
    },
    "execution": {"max_parallel": 4},
    "postprocessing": {".21": {"executable": "usbsuw"}},
}


def test_load_config_from_dict():
    cfg = load_config(RAW)
    assert isinstance(cfg, Config)
    assert cfg.fluka.input == Path("example.inp")
    assert cfg.fluka.custom_executable is None
    assert cfg.fluka.rfluka_path is None
    assert cfg.output_dir == Path("results/")
    assert cfg.grid.parameters == {"beame": [0.05, 0.5], "mat": ["GALLIUM"]}
    assert cfg.grid.runs_per_combo == 3
    assert cfg.execution.max_parallel == 4
    assert cfg.postprocessing == {".21": "usbsuw"}


def test_load_config_from_file(tmp_path):
    import yaml
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(RAW))
    cfg = load_config(cfg_file)
    assert cfg.grid.runs_per_combo == 3
