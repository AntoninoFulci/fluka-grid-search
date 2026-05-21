import importlib.util
import json
import sys
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock


def run_sentinel(args: list[str]):
    spec = importlib.util.spec_from_file_location(
        "sentinel", Path(__file__).parent.parent / "sentinel.py"
    )
    mod = importlib.util.module_from_spec(spec)
    with patch.object(sys, "argv", ["sentinel.py"] + args):
        spec.loader.exec_module(mod)
    return mod


def make_state(tmp_path, combo, job_ids):
    state = {
        combo: {
            "status": "submitted",
            "parameters": {},
            "runs": {
                f"run_{i+1:04d}": {"ts_job_id": jid, "status": "submitted"}
                for i, jid in enumerate(job_ids)
            },
        }
    }
    (tmp_path / "state.json").write_text(json.dumps(state))


def make_config(tmp_path):
    inp = tmp_path / "example.inp"
    inp.write_text("#define beame 0.5\nRANDOMIZ         1.0\nSTOP\n")
    cfg = {
        "fluka": {"input": str(inp), "custom_executable": None, "rfluka_path": "/fluka/bin"},
        "output": {"directory": str(tmp_path)},
        "grid": {"parameters": {"beame": [0.5]}, "runs_per_combo": 1},
        "execution": {"max_parallel": 2},
        "postprocessing": {},
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(cfg))
    return cfg_path


def test_sentinel_waits_for_all_job_ids(tmp_path):
    combo = "beame0.5"
    job_ids = ["10", "11", "12"]
    make_state(tmp_path, combo, job_ids)
    cfg_path = make_config(tmp_path)

    waited = []

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["ts", "-w"]:
            waited.append(cmd[2])
        r = MagicMock()
        r.stdout = "E-Level: 0\n"
        r.stderr = ""
        r.returncode = 0
        return r

    with patch("subprocess.run", side_effect=fake_run):
        run_sentinel([str(cfg_path), str(tmp_path), combo] + job_ids)

    assert sorted(waited) == sorted(job_ids)


def test_sentinel_marks_combo_done(tmp_path):
    combo = "beame0.5"
    make_state(tmp_path, combo, ["5"])
    cfg_path = make_config(tmp_path)

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.stdout = "E-Level: 0\n"
        r.stderr = ""
        r.returncode = 0
        return r

    with patch("subprocess.run", side_effect=fake_run):
        run_sentinel([str(cfg_path), str(tmp_path), combo, "5"])

    state = json.loads((tmp_path / "state.json").read_text())
    assert state[combo]["status"] == "done"


def test_sentinel_marks_combo_partial_on_failure(tmp_path):
    combo = "beame0.5"
    make_state(tmp_path, combo, ["5", "6"])
    cfg_path = make_config(tmp_path)

    codes = {"5": 0, "6": 1}

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        if cmd[:2] == ["ts", "-i"]:
            r.stdout = f"E-Level: {codes[cmd[2]]}\n"
        else:
            r.stdout = ""
        r.stderr = ""
        r.returncode = 0
        return r

    with patch("subprocess.run", side_effect=fake_run):
        run_sentinel([str(cfg_path), str(tmp_path), combo, "5", "6"])

    state = json.loads((tmp_path / "state.json").read_text())
    assert state[combo]["status"] == "partial"
