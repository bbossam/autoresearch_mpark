from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .base import Agent, AgentOutcome


@dataclass
class SessionSnapshot:
    """Everything the ContextAgent needs to brief a fresh session.

    Gathered from disk by the CLI; the agent itself reads no files.
    """

    leaderboard: dict[str, dict] = field(default_factory=dict)
    statuses: list[dict] = field(default_factory=list)
    pending_ideas: list[str] = field(default_factory=list)
    contracts: list[str] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    recent_reviews: list[dict] = field(default_factory=list)
    mistakes: list[dict] = field(default_factory=list)


class ContextAgent(Agent):
    """Restores cross-session context — the "where did I leave off" briefing.

    Run it when the machine comes back up: it summarises the leaderboard,
    in-flight and hung runs, ideas still waiting to be planned, recent review
    verdicts, and the mistakes ledger, so a multi-day campaign can resume
    without re-reading every artifact by hand.
    """

    name = "ContextAgent"

    def brief(self, snapshot: SessionSnapshot) -> AgentOutcome:
        running = [s for s in snapshot.statuses if s.get("state") == "running"]
        hung = [
            s for s in snapshot.statuses
            if s.get("state") in ("stalled", "timeout")
        ]
        briefing = self._render(snapshot, running, hung)
        issues = [
            f"hung run needs attention: {s.get('run_id', '?')}" for s in hung
        ]
        return AgentOutcome(
            agent="ContextAgent",
            ok=not hung,
            summary=(
                f"{len(snapshot.contracts)} contracts, {len(running)} running, "
                f"{len(hung)} hung, {len(snapshot.pending_ideas)} ideas pending"
            ),
            issues=issues,
            data={
                "briefing": briefing,
                "running": [s.get("run_id") for s in running],
                "hung": [s.get("run_id") for s in hung],
                "pending_ideas": snapshot.pending_ideas,
                "mistakes": len(snapshot.mistakes),
            },
        )

    @staticmethod
    def _render(
        snapshot: SessionSnapshot, running: list[dict], hung: list[dict]
    ) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"# Autoresearch session briefing — {now}",
            "",
            "## Runs",
            f"- contracts planned: {len(snapshot.contracts)}",
            f"- results recorded: {len(snapshot.results)}",
            f"- running now: {len(running)}"
            + (f" — {', '.join(s.get('run_id', '?') for s in running)}" if running else ""),
            f"- HUNG (needs attention): {len(hung)}"
            + (f" — {', '.join(s.get('run_id', '?') for s in hung)}" if hung else ""),
            "",
            "## Leaderboard — best so far",
        ]
        if snapshot.leaderboard:
            for key, entry in sorted(snapshot.leaderboard.items()):
                lines.append(
                    f"- {key}: {entry.get('value')} (run {entry.get('run_id')})"
                )
        else:
            lines.append("- (empty)")

        lines += ["", "## Ideas waiting to be planned"]
        if snapshot.pending_ideas:
            lines += [f"- {idea}" for idea in snapshot.pending_ideas]
        else:
            lines.append("- (none)")

        verdicts = Counter(
            r.get("verdict", "unknown") for r in snapshot.recent_reviews
        )
        lines += [
            "",
            "## Reviews",
            f"- kept: {verdicts.get('keep', 0)}  |  "
            f"flagged: {verdicts.get('flag', 0)}  |  "
            f"discarded: {verdicts.get('discard', 0)}",
        ]

        lines += [
            "",
            f"## Known mistakes — do NOT repeat ({len(snapshot.mistakes)})",
        ]
        if snapshot.mistakes:
            for mistake in snapshot.mistakes[-8:]:
                lines.append(
                    f"- {mistake.get('hypothesis', '?')} "
                    f"— failed: {mistake.get('reason', '?')}"
                )
        else:
            lines.append("- (none yet)")
        lines.append("")
        return "\n".join(lines)
