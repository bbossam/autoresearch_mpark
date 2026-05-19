from __future__ import annotations

from ..metrics import higher_is_better, passes
from ..models import AcceptRule, GuardrailMetric, RunContract, RunResult
from .base import Agent, AgentOutcome


class AnalysisAgent(Agent):
    """Judges a finished run against its accept rules and guardrails, and
    reports whether it beats the best result recorded so far.
    """

    name = "AnalysisAgent"

    def analyze(
        self,
        contract: RunContract,
        result: RunResult,
        prior_best: float | None = None,
    ) -> AgentOutcome:
        issues: list[str] = []
        for rule in contract.accept_rules:
            issues += self._check(rule, result, "accept_rule")
        for guard in contract.guardrail_metrics:
            issues += self._check(guard, result, "guardrail")

        direction = self._primary_direction(contract)
        primary = result.metrics.get(contract.primary_metric)
        beats_best: bool | None = None
        if prior_best is not None and primary is not None and direction is not None:
            beats_best = primary > prior_best if direction else primary < prior_best
            if not beats_best:
                issues.append(
                    f"primary metric {contract.primary_metric} does not beat the "
                    f"best so far ({primary} vs {prior_best}) — hill-climbing rule"
                )

        accepted = not issues

        return AgentOutcome(
            agent=self.name,
            ok=accepted,
            summary="accepted" if accepted else f"rejected: {len(issues)} failing check(s)",
            issues=issues,
            data={
                "accepted": accepted,
                "beats_best": beats_best,
                "primary_higher_is_better": direction,
            },
        )

    def render_report(
        self, contract: RunContract, result: RunResult, outcome: AgentOutcome
    ) -> str:
        """Render a human-readable Markdown report for a finished run."""
        lines = [
            f"# Analysis report — {contract.run_id}",
            "",
            f"- target project: {contract.target_project}",
            f"- hypothesis: {contract.hypothesis}",
            f"- primary metric: {contract.primary_metric}",
            f"- verdict: {'ACCEPTED' if outcome.ok else 'REJECTED'}",
        ]
        beats = outcome.data.get("beats_best")
        if beats is not None:
            lines.append(f"- beats best so far: {beats}")
        lines += ["", "## Metrics"]
        if result.metrics:
            lines += [f"- {k}: {v}" for k, v in sorted(result.metrics.items())]
        else:
            lines.append("- (none reported)")
        if outcome.issues:
            lines += ["", "## Failing checks"]
            lines += [f"- {issue}" for issue in outcome.issues]
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _check(
        rule: AcceptRule | GuardrailMetric, result: RunResult, kind: str
    ) -> list[str]:
        if rule.metric not in result.metrics:
            if rule.required:
                return [f"{kind}: required metric {rule.metric!r} missing from result"]
            return []
        value = result.metrics[rule.metric]
        if passes(value, rule.operator, rule.threshold):
            return []
        msg = (
            f"{kind} failed: {rule.metric} {rule.operator.value} "
            f"{rule.threshold} (got {value})"
        )
        return [msg] if rule.required else []

    @staticmethod
    def _primary_direction(contract: RunContract) -> bool | None:
        for rule in contract.accept_rules:
            if rule.metric == contract.primary_metric:
                return higher_is_better(rule.operator)
        return None
