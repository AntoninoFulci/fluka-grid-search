from __future__ import annotations
import json
from pathlib import Path


class StateManager:
    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        self.data: dict = {}

    def load(self) -> None:
        if self.state_file.exists():
            self.data = json.loads(self.state_file.read_text())

    def save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.data, indent=2))

    def _require_combo(self, combo: str) -> None:
        if combo not in self.data:
            raise KeyError(f"Unknown combo {combo!r}; call init_combo first")

    def _require_run(self, combo: str, run: str) -> None:
        self._require_combo(combo)
        if run not in self.data[combo]["runs"]:
            raise KeyError(f"Unknown run {run!r} in combo {combo!r}")

    def init_combo(self, combo: str, params: dict, n_runs: int) -> None:
        self.data[combo] = {
            "status": "pending",
            "parameters": params,
            "runs": {
                f"run_{i:04d}": {"status": "pending"}
                for i in range(1, n_runs + 1)
            },
        }

    def get_combo_status(self, combo: str) -> str:
        return self.data.get(combo, {}).get("status", "pending")

    def set_run_submitted(self, combo: str, run: str, ts_job_id: str) -> None:
        self._require_run(combo, run)
        self.data[combo]["runs"][run]["ts_job_id"] = ts_job_id
        self.data[combo]["runs"][run]["status"] = "submitted"

    def set_run_done(self, combo: str, run: str, exit_code: int) -> None:
        self._require_run(combo, run)
        self.data[combo]["runs"][run]["exit_code"] = exit_code
        self.data[combo]["runs"][run]["status"] = "done" if exit_code == 0 else "failed"

    def set_sentinel(self, combo: str, ts_job_id: str) -> None:
        self._require_combo(combo)
        self.data[combo]["sentinel_ts_job_id"] = ts_job_id

    def set_combo_status(self, combo: str, status: str) -> None:
        self._require_combo(combo)
        self.data[combo]["status"] = status

    def get_pending_combos(self) -> list[str]:
        return [c for c, v in self.data.items() if v["status"] == "pending"]

    def get_in_progress_combos(self) -> list[str]:
        return [
            c for c, v in self.data.items()
            if v["status"] in ("submitted", "running", "postprocessing")
        ]
