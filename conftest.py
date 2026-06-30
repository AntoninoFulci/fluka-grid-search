"""Make the test suite runnable without installing anything.

Mirrors the sys.path bootstrap in run_grid.py: puts this repo (for `grid_search`)
and the bundled FlukaQueueSub submodule (for `backends` / `core`) on sys.path so
imports resolve without `pip install`.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _p in (_ROOT, _ROOT / "external" / "FlukaQueueSub"):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)
