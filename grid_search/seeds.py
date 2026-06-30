from __future__ import annotations
from pathlib import Path

from core.fluka import allocate_seed, parse_randomiz


def scan_used_seeds(output_dir: Path) -> set[int]:
    """Collect RANDOMIZ seeds from every <combo>/run_*/*.inp under output_dir."""
    root = Path(output_dir)
    used: set[int] = set()
    if not root.is_dir():
        return used
    for inp in root.glob("*/run_*/simulation_*.inp"):
        seed = parse_randomiz(inp)
        if seed is not None:
            used.add(seed)
    return used


def next_seed(used: set[int]) -> int:
    """Allocate a fresh seed not in `used`; records it in `used` and returns it."""
    return allocate_seed(used)


def find_duplicate_seeds(output_dir: Path) -> dict[int, list[Path]]:
    """Return seeds shared by more than one run input under output_dir."""
    root = Path(output_dir)
    seeds: dict[int, list[Path]] = {}
    if not root.is_dir():
        return {}
    for inp in sorted(root.glob("*/run_*/simulation_*.inp")):
        seed = parse_randomiz(inp)
        if seed is not None:
            seeds.setdefault(seed, []).append(inp)
    return {s: files for s, files in seeds.items() if len(files) > 1}
