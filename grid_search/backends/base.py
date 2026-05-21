from abc import ABC, abstractmethod
from pathlib import Path


class ExecutionBackend(ABC):
    @abstractmethod
    def submit(self, command: list[str], working_dir: Path) -> str:
        """Submit a job. Returns backend-specific job ID string."""

    @abstractmethod
    def wait(self, job_id: str) -> None:
        """Block until job completes."""

    @abstractmethod
    def get_exit_code(self, job_id: str) -> int:
        """Return exit code of a completed job."""

    @abstractmethod
    def set_max_parallel(self, n: int) -> None:
        """Set maximum number of simultaneously running jobs."""
