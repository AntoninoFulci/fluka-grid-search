from __future__ import annotations
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
        for line in result.stdout.splitlines():
            if line.startswith("E-Level:"):
                try:
                    return int(line.split(":", 1)[1].strip())
                except ValueError:
                    return -1
        return -1

    def set_max_parallel(self, n: int) -> None:
        subprocess.run(["ts", "-S", str(n)], check=True)
