from pathlib import Path
import pytest
import yaml
from unittest.mock import patch
from grid_search.config import load_config, Config, FlukaConfig, GridConfig, ExecutionConfig, validate_config


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
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(RAW))
    cfg = load_config(cfg_file)
    assert cfg.grid.runs_per_combo == 3
    assert cfg.fluka.input == Path("example.inp")
    assert cfg.postprocessing == {".21": "usbsuw"}
    assert cfg.fluka.custom_executable is None


MINIMAL_INP = """\
#define beame 0.5
#define mat GALLIUM
RANDOMIZ         1.0
START         10000.
STOP
"""


def test_validate_config_passes(tmp_path):
    inp = tmp_path / "example.inp"
    inp.write_text(MINIMAL_INP)
    raw = {**RAW, "fluka": {**RAW["fluka"], "input": str(inp)}}
    cfg = load_config(raw)
    with patch("grid_search.config.subprocess.run") as mock_run:
        mock_run.return_value.stdout = "/usr/local/fluka/bin\n"
        mock_run.return_value.returncode = 0
        validate_config(cfg)  # should not raise


def test_validate_config_missing_define(tmp_path):
    inp = tmp_path / "example.inp"
    inp.write_text("#define mat GALLIUM\nSTOP\n")  # missing beame
    raw = {**RAW, "fluka": {**RAW["fluka"], "input": str(inp)}}
    cfg = load_config(raw)
    with pytest.raises(ValueError, match="beame"):
        validate_config(cfg)


def test_validate_config_fluka_not_found(tmp_path):
    inp = tmp_path / "example.inp"
    inp.write_text(MINIMAL_INP)
    raw = {**RAW, "fluka": {**RAW["fluka"], "input": str(inp)}}
    cfg = load_config(raw)
    with patch("grid_search.config.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError
        with pytest.raises(RuntimeError, match="fluka-config"):
            validate_config(cfg)
