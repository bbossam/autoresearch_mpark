"""Append-only ledger of failed experiments.

So the system never re-hypothesises a known dead end: rejected runs (from
``analyze``) and discarded runs (from ``review``) are recorded here, and the
ResearchAgent is shown this list so it proposes genuinely different ideas.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class MistakeLedger:
    """Failed experiments, persisted as JSON, keyed by ``run_id``.

    Re-recording the same ``run_id`` updates its entry (a run fails once).
    """

    def __init__(self, path: str | Path = "experiments/mistakes.json"):
        self.path = Path(path)
        self._entries: dict[str, dict] = {}
        if self.path.exists():
            for entry in json.loads(self.path.read_text(encoding="utf-8")):
                self._entries[entry["run_id"]] = entry

    def record(
        self,
        run_id: str,
        target_project: str,
        hypothesis: str,
        reason: str,
        *,
        source: str,
    ) -> None:
        """Add (or replace) a failure entry. ``source`` is e.g. analyze/review."""
        self._entries[run_id] = {
            "run_id": run_id,
            "target_project": target_project,
            "hypothesis": hypothesis,
            "reason": reason,
            "source": source,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

    def all(self) -> list[dict]:
        return sorted(self._entries.values(), key=lambda e: e["recorded_at"])

    def for_project(self, target_project: str) -> list[dict]:
        return [e for e in self.all() if e["target_project"] == target_project]

    def as_prompt_text(self, target_project: str, limit: int = 40) -> str:
        """The recent failures for a project, formatted for an LLM prompt."""
        entries = self.for_project(target_project)[-limit:]
        return "\n".join(
            f"- {e['hypothesis']} — failed: {e['reason']}" for e in entries
        )

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.all(), indent=2) + "\n", encoding="utf-8"
        )
        return self.path
