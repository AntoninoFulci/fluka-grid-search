from pathlib import Path
from unittest.mock import patch, MagicMock
from grid_search.postprocess import run_postprocessing


def test_run_postprocessing_stdin_format(tmp_path):
    combo_dir = tmp_path / "beame0.05_matGALLIUM"
    run1 = combo_dir / "run_0001"
    run2 = combo_dir / "run_0002"
    run1.mkdir(parents=True)
    run2.mkdir(parents=True)
    (run1 / "sim001.21").write_text("")
    (run2 / "sim002.21").write_text("")

    with patch("grid_search.postprocess.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_postprocessing(combo_dir, {".21": "usbsuw"}, [run1, run2])

    call_kwargs = mock_run.call_args
    assert call_kwargs[0][0] == ["usbsuw"]
    stdin_input = call_kwargs[1]["input"]
    assert str(run1 / "sim001.21") in stdin_input
    assert str(run2 / "sim002.21") in stdin_input
    assert "\n\n" in stdin_input  # empty line terminates file list
    assert stdin_input.endswith("merged_21\n")  # output filename follows

    # Assert ordering: run1 file comes before run2 file since run1 sorts before run2
    idx1 = stdin_input.index(str(run1 / "sim001.21"))
    idx2 = stdin_input.index(str(run2 / "sim002.21"))
    assert idx1 < idx2


def test_run_postprocessing_creates_postproc_dir(tmp_path):
    combo_dir = tmp_path / "combo"
    run1 = combo_dir / "run_0001"
    run1.mkdir(parents=True)
    (run1 / "out.21").write_text("")

    with patch("grid_search.postprocess.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        run_postprocessing(combo_dir, {".21": "usbsuw"}, [run1])

    assert (combo_dir / "postproc").is_dir()


def test_run_postprocessing_skips_missing_extension(tmp_path):
    combo_dir = tmp_path / "combo"
    run1 = combo_dir / "run_0001"
    run1.mkdir(parents=True)
    # no .21 files

    with patch("grid_search.postprocess.subprocess.run") as mock_run:
        run_postprocessing(combo_dir, {".21": "usbsuw"}, [run1])

    mock_run.assert_not_called()


def test_run_postprocessing_saves_log(tmp_path):
    combo_dir = tmp_path / "combo"
    run1 = combo_dir / "run_0001"
    run1.mkdir(parents=True)
    (run1 / "out.21").write_text("")

    with patch("grid_search.postprocess.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="merged ok", stderr="")
        run_postprocessing(combo_dir, {".21": "usbsuw"}, [run1])

    log = combo_dir / "postproc" / "usbsuw.log"
    assert log.exists()
    assert "merged ok" in log.read_text()
