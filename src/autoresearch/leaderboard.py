from __future__ import annotations

import json
from pathlib import Path


class Leaderboard:
    """Persistent best-metric-so-far store — the hill-climbing memory.

    Mirrors the keep/revert loop of Karpathy-style autoresearch: a run is a
    genuine improvement only when it beats the recorded best for its metric.
    Entries are keyed by ``<project>::<metric>``.
    """

    def __init__(self, path: str | Path = "experiments/leaderboard.json"):
        self.path = Path(path)
        self._data: dict[str, dict] = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def _key(project: str, metric: str) -> str:
        return f"{project}::{metric}"

    def best(self, project: str, metric: str) -> dict | None:
        """Return the recorded best entry for a project/metric, or None."""
        return self._data.get(self._key(project, metric))

    def entries(self) -> dict[str, dict]:
        """All recorded bests, keyed by ``<project>::<metric>``."""
        return dict(self._data)

    def remove(self, key: str) -> bool:
        """Delete an entry by its ``<project>::<metric>`` key.

        Returns True if the entry existed. Call ``save()`` to persist.
        """
        return self._data.pop(key, None) is not None

    def record(
        self,
        project: str,
        metric: str,
        value: float,
        run_id: str,
        higher_is_better: bool | None,
    ) -> bool:
        """Store ``value`` if it is the new best. Returns True when it is.

        With ``higher_is_better=None`` (unranked metric) only the first value
        is ever recorded.
        """
        key = self._key(project, metric)
        current = self._data.get(key)
        if current is None:
            is_best = True
        elif higher_is_better is None:
            is_best = False
        elif higher_is_better:
            is_best = value > current["value"]
        else:
            is_best = value < current["value"]
        if is_best:
            self._data[key] = {
                "value": value,
                "run_id": run_id,
                "higher_is_better": higher_is_better,
            }
        return is_best

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return self.path
