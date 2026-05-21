from __future__ import annotations
import subprocess
from pathlib import Path


def run_postprocessing(
    combo_dir: Path,
    postprocessing: dict[str, str],
    successful_run_dirs: list[Path],
) -> None:
    postproc_dir = combo_dir / "postproc"
    postproc_dir.mkdir(parents=True, exist_ok=True)

    for extension, executable in postprocessing.items():
        files = [
            f
            for run_dir in successful_run_dirs
            for f in sorted(run_dir.glob(f"*{extension}"))
        ]
        if not files:
            continue

        stdin_input = "\n".join(str(f) for f in files) + "\n\n"
        result = subprocess.run(
            [executable],
            input=stdin_input,
            text=True,
            capture_output=True,
            cwd=postproc_dir,
        )
        log_path = postproc_dir / f"{executable}.log"
        log_path.write_text(result.stdout + result.stderr)
