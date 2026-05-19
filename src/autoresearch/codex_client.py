"""Execution-layer wrapper for invoking the Codex CLI.

The ReviewAgent is pure; this module is the side-effecting half it delegates
to. The Codex command is configurable via the ``AUTORESEARCH_CODEX_CMD``
environment variable (default: ``codex exec``).
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess

DEFAULT_CODEX_CMD = ["codex", "exec"]


class CodexError(RuntimeError):
    """Raised when the Codex CLI is missing, fails, or times out."""


def codex_command() -> list[str]:
    """The Codex invocation, from ``AUTORESEARCH_CODEX_CMD`` or the default."""
    raw = os.environ.get("AUTORESEARCH_CODEX_CMD")
    return shlex.split(raw) if raw else list(DEFAULT_CODEX_CMD)


def codex_available() -> bool:
    """True when the configured Codex executable is on PATH."""
    return shutil.which(codex_command()[0]) is not None


def run_codex(prompt: str, *, timeout: float = 300.0) -> str:
    """Run the Codex CLI on ``prompt`` and return its stdout.

    Raises CodexError if the CLI is absent, exits non-zero, or times out — so
    a single unreviewable run never stalls a long batch.
    """
    command = codex_command()
    if shutil.which(command[0]) is None:
        raise CodexError(
            f"Codex CLI {command[0]!r} not found on PATH; install it or set "
            "AUTORESEARCH_CODEX_CMD"
        )
    try:
        proc = subprocess.run(
            [*command, prompt],
            check=True,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodexError(f"Codex review timed out after {timeout}s") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or f"exit code {exc.returncode}"
        raise CodexError(f"Codex CLI failed: {detail}") from exc
    return proc.stdout
