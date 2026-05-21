from pathlib import Path
from grid_search.workspace import create_run_workspace, patch_inp, generate_seed

TEMPLATE_INP = """\
#define beame 0.5
#define mat GALLIUM
BEAM          $beame                                                  ELECTRON
ASSIGNMA        $mat    TARGET
RANDOMIZ         1.0
START         10000.
STOP
"""


def test_create_run_workspace(tmp_path):
    ws = create_run_workspace(tmp_path, "beame0.05_matGALLIUM", 1)
    assert ws == tmp_path / "beame0.05_matGALLIUM" / "run_0001"
    assert ws.is_dir()


def test_create_run_workspace_zero_padding(tmp_path):
    ws = create_run_workspace(tmp_path, "combo", 42)
    assert ws.name == "run_0042"


def test_patch_inp_replaces_defines(tmp_path):
    template = tmp_path / "template.inp"
    template.write_text(TEMPLATE_INP)
    out = tmp_path / "patched.inp"
    patch_inp(template, out, {"beame": 0.1, "mat": "TUNGSTEN"}, seed=12345678)
    text = out.read_text()
    assert "#define beame 0.1\n" in text
    assert "#define mat TUNGSTEN\n" in text
    assert "#define beame 0.5" not in text
    assert "#define mat GALLIUM" not in text


def test_patch_inp_replaces_seed(tmp_path):
    template = tmp_path / "template.inp"
    template.write_text(TEMPLATE_INP)
    out = tmp_path / "patched.inp"
    patch_inp(template, out, {"beame": 0.5, "mat": "GALLIUM"}, seed=99999999)
    text = out.read_text()
    assert "RANDOMIZ" in text
    assert "99999999" in text
    assert "RANDOMIZ         1.0" not in text


def test_patch_inp_preserves_other_lines(tmp_path):
    template = tmp_path / "template.inp"
    template.write_text(TEMPLATE_INP)
    out = tmp_path / "patched.inp"
    patch_inp(template, out, {"beame": 0.5, "mat": "GALLIUM"}, seed=1)
    text = out.read_text()
    assert "START         10000." in text
    assert "STOP" in text


def test_patch_inp_does_not_touch_body_refs(tmp_path):
    template = tmp_path / "template.inp"
    template.write_text(TEMPLATE_INP)
    out = tmp_path / "patched.inp"
    patch_inp(template, out, {"beame": 0.1, "mat": "TUNGSTEN"}, seed=1)
    text = out.read_text()
    assert "BEAM          $beame" in text
    assert "ASSIGNMA        $mat" in text


def test_generate_seed_range():
    for _ in range(100):
        s = generate_seed()
        assert 1 <= s <= int(9e7)
