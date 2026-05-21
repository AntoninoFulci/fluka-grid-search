import json
from pathlib import Path
from grid_search.state import StateManager


def test_init_combo(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.init_combo("beame0.05_matGALLIUM", {"beame": 0.05, "mat": "GALLIUM"}, n_runs=3)
    assert sm.get_combo_status("beame0.05_matGALLIUM") == "pending"
    runs = sm.data["beame0.05_matGALLIUM"]["runs"]
    assert list(runs.keys()) == ["run_0001", "run_0002", "run_0003"]
    assert all(r["status"] == "pending" for r in runs.values())


def test_save_and_load(tmp_path):
    path = tmp_path / "state.json"
    sm = StateManager(path)
    sm.init_combo("combo1", {"x": 1}, n_runs=2)
    sm.save()
    sm2 = StateManager(path)
    sm2.load()
    assert sm2.get_combo_status("combo1") == "pending"


def test_set_run_submitted(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.init_combo("combo1", {}, n_runs=2)
    sm.set_run_submitted("combo1", "run_0001", "42")
    run = sm.data["combo1"]["runs"]["run_0001"]
    assert run["ts_job_id"] == "42"
    assert run["status"] == "submitted"


def test_set_run_done(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.init_combo("combo1", {}, n_runs=1)
    sm.set_run_submitted("combo1", "run_0001", "7")
    sm.set_run_done("combo1", "run_0001", exit_code=0)
    assert sm.data["combo1"]["runs"]["run_0001"]["exit_code"] == 0
    assert sm.data["combo1"]["runs"]["run_0001"]["status"] == "done"


def test_set_combo_status(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.init_combo("combo1", {}, n_runs=1)
    sm.set_combo_status("combo1", "done")
    assert sm.get_combo_status("combo1") == "done"


def test_get_pending_combos(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.init_combo("combo1", {}, n_runs=1)
    sm.init_combo("combo2", {}, n_runs=1)
    sm.set_combo_status("combo2", "done")
    assert sm.get_pending_combos() == ["combo1"]


def test_load_missing_file(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.load()  # should not raise; starts with empty state
    assert sm.data == {}
