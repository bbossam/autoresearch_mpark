from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..models import AcceptRule, IdeaSpec, MetricOperator
from .base import Agent, AgentOutcome

CodexRunner = Callable[[str], str]

_OPERATORS = {op.value for op in MetricOperator}


@dataclass
class ResearchContext:
    """Inputs for early-stage ideation — whatever little is known so far."""

    project_id: str
    project_name: str = ""
    description: str = ""
    notes: str = ""
    goal: str = ""
    existing_idea_ids: list[str] = field(default_factory=list)
    prior_findings: str = ""
    known_failures: str = ""


class ResearchAgent(Agent):
    """Aggressively hypothesises research ideas for an early-stage project.

    Given a project and whatever little is known about it, it asks Codex for a
    batch of diverse, ambitious hypotheses and returns them as IdeaSpec drafts
    ready for the PlanningAgent. This is the stage-zero agent — it runs before
    a project has enough signal for incremental tuning.

    Pure: it builds the prompt and parses the response; the Codex call is an
    injected ``codex_runner`` callable.
    """

    name = "ResearchAgent"

    def build_prompt(self, context: ResearchContext, count: int) -> str:
        return _PROMPT_TEMPLATE.format(
            count=count,
            project_id=context.project_id,
            project_name=context.project_name or context.project_id,
            description=context.description or "(none provided)",
            notes=context.notes or "(none)",
            goal=context.goal or "(no specific goal — explore broadly)",
            existing=", ".join(context.existing_idea_ids) or "(none)",
            findings=context.prior_findings or "(none yet)",
            known_failures=context.known_failures or "(none recorded)",
        )

    def hypothesize(
        self,
        context: ResearchContext,
        codex_runner: CodexRunner,
        count: int = 8,
    ) -> tuple[list[IdeaSpec], AgentOutcome]:
        raw = codex_runner(self.build_prompt(context, count))
        return self._parse(context, raw)

    def _parse(
        self, context: ResearchContext, raw: str
    ) -> tuple[list[IdeaSpec], AgentOutcome]:
        items = _extract_json_list(raw)
        if items is None:
            return [], AgentOutcome(
                agent="ResearchAgent",
                ok=False,
                summary="Codex response could not be parsed as a JSON list",
                issues=["unparseable Codex output"],
                data={"raw": raw},
            )
        ideas: list[IdeaSpec] = []
        skipped: list[str] = []
        seen = set(context.existing_idea_ids)
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                idea = self._to_idea(context, item, seen)
            except (KeyError, ValueError) as exc:
                skipped.append(str(exc))
                continue
            seen.add(idea.idea_id)
            ideas.append(idea)
        return ideas, AgentOutcome(
            agent="ResearchAgent",
            ok=bool(ideas),
            summary=f"hypothesised {len(ideas)} idea(s)"
            + (f", skipped {len(skipped)}" if skipped else ""),
            issues=skipped,
            data={"idea_ids": [i.idea_id for i in ideas], "raw": raw},
        )

    @staticmethod
    def _to_idea(
        context: ResearchContext, item: dict, seen: set[str]
    ) -> IdeaSpec:
        hypothesis = str(item.get("hypothesis", "")).strip()
        if not hypothesis:
            raise ValueError("idea missing 'hypothesis'")
        primary_metric = str(item.get("primary_metric", "")).strip()
        if not primary_metric:
            raise ValueError(f"idea missing 'primary_metric': {hypothesis[:60]}")
        idea_id = base = _slugify(item.get("idea_id") or hypothesis)
        suffix = 2
        while idea_id in seen:
            idea_id = f"{base}-{suffix}"
            suffix += 1
        accept_rules: list[AcceptRule] = []
        operator = str(item.get("accept_operator", "")).strip().lower()
        threshold = item.get("accept_threshold")
        if operator in _OPERATORS and isinstance(threshold, (int, float)):
            accept_rules = [
                AcceptRule(
                    metric=primary_metric,
                    operator=MetricOperator(operator),
                    threshold=float(threshold),
                )
            ]
        return IdeaSpec(
            idea_id=idea_id,
            target_project=context.project_id,
            hypothesis=hypothesis,
            primary_metric=primary_metric,
            accept_rules=accept_rules,
            notes=str(item.get("rationale", "")).strip(),
        )


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return slug[:48].rstrip("-") or "idea"


def _extract_json_list(text: str) -> list | None:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


_PROMPT_TEMPLATE = """You are the research ideation agent for an EARLY-STAGE research project.
Aggressively propose {count} diverse, ambitious, testable hypotheses.

Project: {project_name} (id: {project_id})
Description: {description}
Project notes: {notes}
Research goal: {goal}
Existing idea ids (do NOT repeat these): {existing}
Prior findings: {findings}
Known FAILED hypotheses (do NOT re-propose these or close variants): {known_failures}

Respond with ONLY a JSON array of exactly {count} objects, no prose. Each
object has exactly these keys:
  "idea_id": short kebab-case slug, unique
  "hypothesis": one sentence - a concrete, falsifiable claim
  "primary_metric": the single metric that would confirm or refute it
  "accept_operator": one of "gt", "gte", "lt", "lte" - the success direction
  "accept_threshold": a number the primary_metric must beat for the idea to pass
  "rationale": one or two sentences on why it is promising

Be bold: prefer high-variance, non-obvious directions over safe increments.
Steer well clear of the known failures above - autoresearch must not repeat mistakes.
Each hypothesis must be specific enough to become exactly one experiment.
"""
