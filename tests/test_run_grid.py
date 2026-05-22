import importlib.util
import json
import sys
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


def make_project(tmp_path):
    inp = tmp_path / "example.inp"
    inp.write_text("#define beame 0.5\n#define mat GALLIUM\nRANDOMIZ         1.0\nSTOP\n")
    cfg = {
        "fluka": {"input": str(inp), "custom_executable": None, "rfluka_path": "/fluka/bin"},
        "output": {"directory": str(tmp_path / "results")},
        "grid": {"parameters": {"beame": [0.05, 0.1], "mat": ["GALLIUM"]}, "runs_per_combo": 2},
        "execution": {"max_parallel": 4},
        "postprocessing": {},
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(cfg))
    return cfg_path


def run_main(argv):
    spec = importlib.util.spec_from_file_location(
        "run_grid", Path(__file__).parent.parent / "run_grid.py"
    )
    mod = importlib.util.module_from_spec(spec)
    with patch.object(sys, "argv", ["run_grid.py"] + argv):
        spec.loader.exec_module(mod)
        mod.main()
    return mod


def test_dry_run_submits_nothing(tmp_path, capsys):
    cfg_path = make_project(tmp_path)
    with patch("subprocess.run") as mock_run:
        run_main([str(cfg_path), "--dry-run"])
    for call in mock_run.call_args_list:
        assert call[0][0][0] != "ts"
    out = capsys.readouterr().out
    assert "[dry-run]" in out


def test_submits_correct_number_of_jobs(tmp_path):
    cfg_path = make_project(tmp_path)
    submitted = []

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.stdout = str(len(submitted)) + "\n"
        r.returncode = 0
        submitted.append(cmd)
        return r

    with patch("subprocess.run", side_effect=fake_run):
        run_main([str(cfg_path)])

    ts_submissions = [c for c in submitted if c[0] == "ts"]
    # 2 combos × (2 runs + 1 sentinel) = 6 ts calls + 1 ts -S call = 7
    assert len(ts_submissions) == 7


def test_state_written_after_submit(tmp_path):
    cfg_path = make_project(tmp_path)
    job_counter = [0]

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        job_counter[0] += 1
        r.stdout = str(job_counter[0]) + "\n"
        r.returncode = 0
        return r

    with patch("subprocess.run", side_effect=fake_run):
        run_main([str(cfg_path)])

    state_file = tmp_path / "results" / "state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert "beame0.05_matGALLIUM" in state
    assert "beame0.1_matGALLIUM" in state


def test_skips_done_combos(tmp_path):
    cfg_path = make_project(tmp_path)
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    state = {
        "beame0.05_matGALLIUM": {"status": "done", "parameters": {}, "runs": {}},
        "beame0.1_matGALLIUM": {"status": "pending", "parameters": {}, "runs": {}},
    }
    (results_dir / "state.json").write_text(json.dumps(state))

    submitted = []

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.stdout = str(len(submitted)) + "\n"
        r.returncode = 0
        submitted.append(cmd)
        return r

    with patch("subprocess.run", side_effect=fake_run):
        run_main([str(cfg_path)])

    ts_submissions = [c for c in submitted if c[0] == "ts" and c[1] != "-S"]
    # only 1 combo: 2 runs + 1 sentinel = 3
    assert len(ts_submissions) == 3


def test_reset_deletes_output_dir(tmp_path, monkeypatch):
    cfg_path = make_project(tmp_path)
    results = tmp_path / "results"
    results.mkdir()
    (results / "state.json").write_text("{}")

    monkeypatch.setattr("builtins.input", lambda _: "yes")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="1\n", returncode=0)
        run_main([str(cfg_path), "--reset"])

    state_file = results / "state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert "beame0.05_matGALLIUM" in state  # freshly submitted


def test_reset_aborts_on_no(tmp_path, monkeypatch, capsys):
    cfg_path = make_project(tmp_path)
    results = tmp_path / "results"
    results.mkdir()
    marker = results / "keep_me.txt"
    marker.write_text("important")

    monkeypatch.setattr("builtins.input", lambda _: "no")

    with pytest.raises(SystemExit):
        run_main([str(cfg_path), "--reset"])

    assert marker.exists()
    out = capsys.readouterr().out
    assert "Aborted" in out


def test_postprocess_flag_calls_run_postprocessing(tmp_path):
    cfg_path = make_project(tmp_path)
    results = tmp_path / "results"
    results.mkdir()
    combo = "beame0.05_matGALLIUM"
    run1 = results / combo / "run_0001"
    run1.mkdir(parents=True)
    state = {
        combo: {
            "status": "submitted",
            "parameters": {},
            "runs": {"run_0001": {"status": "done", "exit_code": 0}},
        }
    }
    (results / "state.json").write_text(json.dumps(state))

    with patch("grid_search.postprocess.run_postprocessing") as mock_pp:
        run_main([str(cfg_path), "--postprocess"])

    mock_pp.assert_called_once()
    call_args = mock_pp.call_args[0]
    assert call_args[0] == results / combo
    assert call_args[2] == [run1]


def test_analyze_flag_no_isotope_config_exits(tmp_path, capsys):
    cfg_path = make_project(tmp_path)
    results = tmp_path / "results"
    results.mkdir(exist_ok=True)
    (results / "state.json").write_text("{}")

    with pytest.raises(SystemExit):
        run_main([str(cfg_path), "--analyze"])

    out = capsys.readouterr().out
    assert "isotope_analysis" in out


def test_analyze_flag_calls_run_isotope_analysis(tmp_path):
    cfg_path = make_project(tmp_path)
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["isotope_analysis"] = {
        "isotopes": {27: 60},
        "rnc_files": ["merged_21"],
    }
    cfg_path.write_text(yaml.dump(cfg))

    results = tmp_path / "results"
    results.mkdir(exist_ok=True)
    (results / "state.json").write_text("{}")

    with patch("grid_search.isotope_analysis.run_isotope_analysis") as mock_analyze:
        run_main([str(cfg_path), "--analyze"])

    mock_analyze.assert_called_once()
    # Verify the call was made with combo=None (no --combo argument given)
    call_kwargs = mock_analyze.call_args[1]
    assert call_kwargs.get("combo") is None
