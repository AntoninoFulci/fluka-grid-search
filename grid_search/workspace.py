from __future__ import annotations
import random
import re
from pathlib import Path
from typing import Optional


def create_run_workspace(output_dir: Path, combo: str, run_idx: int) -> Path:
    run_dir = output_dir / combo / f"run_{run_idx:04d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def patch_inp(
    template: Path,
    output: Path,
    params: dict,
    seed: int,
    primaries: Optional[int] = None,
) -> None:
    lines = template.read_text().splitlines(keepends=True)
    result = []
    for line in lines:
        patched = line
        for name, value in params.items():
            patched = re.sub(
                rf"^(#define\s+{re.escape(name)}\s+)\S+",
                rf"\g<1>{value}",
                patched,
            )
        if re.match(r"^RANDOMIZ\s", patched):
            patched = f"RANDOMIZ          1.{seed:>10d}\n"
        if primaries is not None and re.match(r"^START\s", patched):
            patched = re.sub(r"^(START\s+)\S+", rf"\g<1>{primaries}.", patched)
        result.append(patched)
    output.write_text("".join(result))


def generate_seed() -> int:
    return random.randint(1, int(9e7))
