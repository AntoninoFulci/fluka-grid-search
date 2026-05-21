from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess
import pytest
from grid_search.backends.task_spooler import TaskSpoolerBackend


def test_submit_returns_job_id(tmp_path):
    backend = TaskSpoolerBackend()
    mock_result = MagicMock()
    mock_result.stdout = "5\n"
    mock_result.returncode = 0
    with patch("grid_search.backends.task_spooler.subprocess.run", return_value=mock_result) as mock_run:
        job_id = backend.submit(["rfluka", "-M", "1", "sim.inp"], tmp_path)
    assert job_id == "5"
    call_args = mock_run.call_args
    assert call_args[0][0] == ["ts", "rfluka", "-M", "1", "sim.inp"]
    assert call_args[1]["cwd"] == tmp_path


def test_submit_raises_on_failure(tmp_path):
    backend = TaskSpoolerBackend()
    with patch("grid_search.backends.task_spooler.subprocess.run", side_effect=subprocess.CalledProcessError(1, "ts")):
        with pytest.raises(subprocess.CalledProcessError):
            backend.submit(["rfluka", "-M", "1", "sim.inp"], tmp_path)


def test_wait_calls_ts_w():
    backend = TaskSpoolerBackend()
    with patch("grid_search.backends.task_spooler.subprocess.run") as mock_run:
        backend.wait("7")
    mock_run.assert_called_once_with(["ts", "-w", "7"], check=True)


def test_get_exit_code_parses_e_level():
    backend = TaskSpoolerBackend()
    ts_info = "ID: 5\nState: finished\nE-Level: 0\nTimes: 1.2/0.1/0.1\n"
    mock_result = MagicMock()
    mock_result.stdout = ts_info
    with patch("grid_search.backends.task_spooler.subprocess.run", return_value=mock_result):
        code = backend.get_exit_code("5")
    assert code == 0


def test_get_exit_code_nonzero():
    backend = TaskSpoolerBackend()
    ts_info = "ID: 6\nState: finished\nE-Level: 1\n"
    mock_result = MagicMock()
    mock_result.stdout = ts_info
    with patch("grid_search.backends.task_spooler.subprocess.run", return_value=mock_result):
        code = backend.get_exit_code("6")
    assert code == 1


def test_set_max_parallel():
    backend = TaskSpoolerBackend()
    with patch("grid_search.backends.task_spooler.subprocess.run") as mock_run:
        backend.set_max_parallel(4)
    mock_run.assert_called_once_with(["ts", "-S", "4"], check=True)
