from __future__ import annotations

import json
from pathlib import Path

from .models import RunResult


def write_run_result(result: RunResult, log_dir: str | Path = "experiments/logs") -> Path:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{result.run_id}.json"
    path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path

