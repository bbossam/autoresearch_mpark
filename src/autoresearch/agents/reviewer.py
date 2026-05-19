from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from .base import Agent, AgentOutcome

CodexRunner = Callable[[str], str]

_VERDICTS = ("keep", "flag", "discard")


@dataclass
class ReviewArtifacts:
    """Bounded text gathered for one run, fed to the reviewer.

    The caller truncates large logs before constructing this — the ReviewAgent
    never reads files itself.
    """

    run_id: str
    target_project: str = ""
    hypothesis: str = ""
    primary_metric: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    log_excerpt: str = ""
    report: str = ""
    diff: str = ""


class ReviewAgent(Agent):
    """Asks Codex whether a run's result is worth a human's attention.

    This is the layer that turns a huge volume of logs and reports into a
    compact, triaged verdict (keep / flag / discard). Reviewing free text needs
    judgement, so — unlike the other agents — it calls an LLM.

    It stays pure all the same: it builds the prompt and parses the response,
    while the actual Codex call is an injected ``codex_runner`` callable. That
    keeps the agent testable and free of I/O.
    """

    name = "ReviewAgent"

    def build_prompt(self, artifacts: ReviewArtifacts) -> str:
        return _PROMPT_TEMPLATE.format(
            run_id=artifacts.run_id,
            hypothesis=artifacts.hypothesis or "(none)",
            primary_metric=artifacts.primary_metric or "(none)",
            metrics=json.dumps(artifacts.metrics, sort_keys=True),
            log=artifacts.log_excerpt or "(no log)",
            report=artifacts.report or "(no report)",
            diff=artifacts.diff or "(no diff)",
        )

    def review(
        self, artifacts: ReviewArtifacts, codex_runner: CodexRunner
    ) -> AgentOutcome:
        raw = codex_runner(self.build_prompt(artifacts))
        return self._parse(raw)

    def render_review(
        self, artifacts: ReviewArtifacts, outcome: AgentOutcome
    ) -> str:
        """Render the Codex verdict as a compact Markdown digest."""
        lines = [
            f"# Review — {artifacts.run_id}",
            "",
            f"- verdict: {str(outcome.data.get('verdict', 'flag')).upper()}",
            f"- interesting: {outcome.data.get('interesting', False)}",
            f"- hypothesis: {artifacts.hypothesis or '(none)'}",
            "",
            "## Summary",
            outcome.data.get("summary") or "(none)",
        ]
        if outcome.issues:
            lines += ["", "## Issues raised"]
            lines += [f"- {issue}" for issue in outcome.issues]
        lines += ["", "## Raw Codex response", "```", outcome.data.get("raw", ""), "```", ""]
        return "\n".join(lines)

    @staticmethod
    def _parse(raw: str) -> AgentOutcome:
        data = _extract_json(raw)
        if data is None:
            return AgentOutcome(
                agent="ReviewAgent",
                ok=False,
                summary="Codex response could not be parsed; needs a human",
                issues=["unparseable Codex output"],
                data={
                    "verdict": "flag",
                    "interesting": True,
                    "summary": raw.strip()[:500],
                    "raw": raw,
                },
            )
        verdict = str(data.get("verdict", "flag")).strip().lower()
        if verdict not in _VERDICTS:
            verdict = "flag"
        issues = [str(i).strip() for i in data.get("issues", []) if str(i).strip()]
        summary = str(data.get("summary", "")).strip()
        return AgentOutcome(
            agent="ReviewAgent",
            ok=verdict == "keep",
            summary=summary or f"review verdict: {verdict}",
            issues=issues,
            data={
                "verdict": verdict,
                "interesting": bool(data.get("interesting", False)),
                "summary": summary,
                "raw": raw,
            },
        )


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of Codex output (tolerates code fences)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


_PROMPT_TEMPLATE = """You are reviewing one automated research experiment. Decide whether it is \
worth a human researcher's attention.

Experiment: {run_id}
Hypothesis: {hypothesis}
Primary metric: {primary_metric}
Reported metrics: {metrics}

--- experiment log (may be truncated) ---
{log}

--- analysis report ---
{report}

--- diff ---
{diff}

Respond with ONLY a JSON object, no prose, with exactly these keys:
  "verdict": one of "keep", "flag", "discard"
  "interesting": true or false
  "summary": one or two plain-text sentences
  "issues": list of short strings (anomalies, errors, suspicious numbers); may be empty

Guidance:
- "keep": a genuine, trustworthy improvement worth integrating.
- "flag": needs a human - surprising result, possible bug, or unclear outcome.
- "discard": no improvement, or clearly broken.
- A tiny improvement that adds large complexity is not worth keeping; deleting
  code while holding the metric is always a win.
"""
