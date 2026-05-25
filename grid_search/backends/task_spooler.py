from __future__ import annotations
import re
import subprocess
from pathlib import Path
from .base import ExecutionBackend


class TaskSpoolerBackend(ExecutionBackend):
    def submit(self, command: list[str], working_dir: Path) -> str:
        result = subprocess.run(
            ["ts"] + command,
            capture_output=True, text=True, check=True, cwd=working_dir,
        )
        return result.stdout.strip()

    def wait(self, job_id: str) -> None:
        subprocess.run(["ts", "-w", job_id], check=True)

    def get_exit_code(self, job_id: str) -> int:
        result = subprocess.run(
            ["ts", "-i", job_id], capture_output=True, text=True,
        )
        match = re.search(r"exit code (\d+)", result.stdout)
        if match:
            return int(match.group(1))
        return -1

    def set_max_parallel(self, n: int) -> None:
        subprocess.run(["ts", "-S", str(n)], check=True)
