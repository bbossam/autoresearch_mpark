"""Real-process watchdog for long, unattended experiment runs.

Runs an experiment command as a subprocess and emits a heartbeat to
``experiments/status/<run_id>.json`` every few seconds. This is the liveness
signal for multi-day sessions of hundreds of experiments:

- **time budget** — a run exceeding ``time_budget_seconds`` is terminated
  (state ``timeout``). This is Karpathy's "fixed budget per run" rule.
- **stall detection** — a run producing no output for ``stall_timeout_seconds``
  is treated as hung and terminated (state ``stalled``).

Both conditions are written into the status file so an agent polling it can
react instead of waiting forever on a hung process.
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import ExperimentStatus


@dataclass
class WatchdogResult:
    run_id: str
    state: str
    exit_code: int | None
    duration_seconds: float
    status_path: Path
    log_path: Path


def _terminate(proc: subprocess.Popen) -> None:
    """Stop the whole process group, gracefully then forcibly.

    The child is launched in its own session (``start_new_session=True``), so
    its process-group id equals its pid; signalling the group also kills any
    experiment subprocesses the command spawned — not just the launcher.
    """
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue


def run_with_watchdog(
    run_id: str,
    command: str | list[str],
    *,
    cwd: str | Path | None = None,
    time_budget_seconds: float = 300.0,
    stall_timeout_seconds: float = 60.0,
    heartbeat_seconds: float = 10.0,
    status_dir: str | Path = "experiments/status",
    log_dir: str | Path = "experiments/logs",
) -> WatchdogResult:
    """Run ``command`` under time-budget and stall supervision.

    Output is streamed to ``<log_dir>/<run_id>.out`` and a heartbeat is written
    to ``<status_dir>/<run_id>.json`` on every cycle.
    """
    status_dir = Path(status_dir)
    log_dir = Path(log_dir)
    status_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    status_path = status_dir / f"{run_id}.json"
    log_path = log_dir / f"{run_id}.out"

    args = shlex.split(command) if isinstance(command, str) else list(command)
    cmd_str = command if isinstance(command, str) else " ".join(command)

    start = time.monotonic()
    started_at = datetime.now(timezone.utc)
    last_output = {"t": start}
    lock = threading.Lock()

    proc = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    log_file = log_path.open("w", encoding="utf-8")

    def _pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            log_file.write(line)
            log_file.flush()
            with lock:
                last_output["t"] = time.monotonic()

    reader = threading.Thread(target=_pump, daemon=True)
    reader.start()

    def _write_status(state: str, exit_code: int | None, note: str = "") -> None:
        now = time.monotonic()
        with lock:
            output_age = now - last_output["t"]
        status = ExperimentStatus(
            run_id=run_id,
            state=state,
            command=cmd_str,
            pid=proc.pid,
            started_at=started_at,
            updated_at=datetime.now(timezone.utc),
            elapsed_seconds=round(now - start, 3),
            last_output_age_seconds=round(output_age, 3),
            exit_code=exit_code,
            time_budget_seconds=time_budget_seconds,
            stall_timeout_seconds=stall_timeout_seconds,
            note=note,
        )
        status_path.write_text(
            status.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

    _write_status("running", None)
    state = "running"
    note = ""
    exit_code: int | None = None

    while True:
        try:
            exit_code = proc.wait(timeout=heartbeat_seconds)
            state = "completed" if exit_code == 0 else "failed"
            break
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            with lock:
                output_age = time.monotonic() - last_output["t"]
            if elapsed > time_budget_seconds:
                state = "timeout"
                note = f"time budget exceeded ({elapsed:.0f}s > {time_budget_seconds}s)"
                _terminate(proc)
                exit_code = proc.wait()
                break
            if output_age > stall_timeout_seconds:
                state = "stalled"
                note = f"no output for {output_age:.0f}s (> {stall_timeout_seconds}s)"
                _terminate(proc)
                exit_code = proc.wait()
                break
            _write_status("running", None)

    reader.join(timeout=2)
    log_file.close()
    duration = round(time.monotonic() - start, 3)
    _write_status(state, exit_code, note)
    return WatchdogResult(
        run_id=run_id,
        state=state,
        exit_code=exit_code,
        duration_seconds=duration,
        status_path=status_path,
        log_path=log_path,
    )
