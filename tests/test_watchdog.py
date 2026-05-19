from __future__ import annotations

import json
import sys
from pathlib import Path

from autoresearch.watchdog import run_with_watchdog


def _run(tmp_path: Path, run_id: str, code: str, **kwargs):
    return run_with_watchdog(
        run_id,
        [sys.executable, "-c", code],
        heartbeat_seconds=0.2,
        status_dir=tmp_path / "status",
        log_dir=tmp_path / "logs",
        **kwargs,
    )


def test_watchdog_completes_normal_command(tmp_path: Path):
    result = _run(
        tmp_path, "wd_ok", "print('hello')",
        time_budget_seconds=10, stall_timeout_seconds=10,
    )

    assert result.state == "completed"
    assert result.exit_code == 0
    status = json.loads(result.status_path.read_text(encoding="utf-8"))
    assert status["state"] == "completed"


def test_watchdog_kills_run_over_time_budget(tmp_path: Path):
    result = _run(
        tmp_path, "wd_timeout", "import time; time.sleep(30)",
        time_budget_seconds=1, stall_timeout_seconds=30,
    )

    assert result.state == "timeout"
    assert result.duration_seconds < 10


def test_watchdog_detects_stalled_run(tmp_path: Path):
    result = _run(
        tmp_path, "wd_stall", "import time; time.sleep(30)",
        time_budget_seconds=30, stall_timeout_seconds=1,
    )

    assert result.state == "stalled"
    assert result.duration_seconds < 10
