from __future__ import annotations

from dataclasses import dataclass

from ..models import RunContract
from .base import Agent, AgentOutcome

# Per-task Codex token range: a trivial task gets MIN, the hardest gets MAX.
MIN_TASK_TOKENS = 2000
MAX_TASK_TOKENS = 40000


@dataclass(frozen=True)
class BudgetView:
    total: int
    consumed: int
    remaining: int
    days_to_reset: int


def estimate_difficulty(contract: RunContract) -> float:
    """Task difficulty in 0.0 (trivial) .. 1.0 (hard), from the contract scope.

    Deterministic — derived from the task itself (file-scope breadth, change
    caps, number of accept/guardrail rules, hypothesis length), so sizing the
    token spend costs no extra Codex call.
    """
    signals = [
        min(contract.max_files_changed / 20, 1.0),
        min(contract.max_lines_changed / 1000, 1.0),
        min(len(contract.allowed_files) / 10, 1.0),
        min((len(contract.accept_rules) + len(contract.guardrail_metrics)) / 8, 1.0),
        min(len(contract.hypothesis) / 400, 1.0),
    ]
    return round(sum(signals) / len(signals), 3)


def difficulty_tokens(difficulty: float) -> int:
    """Map a 0..1 difficulty to a per-task token allocation."""
    difficulty = max(0.0, min(difficulty, 1.0))
    return int(MIN_TASK_TOKENS + difficulty * (MAX_TASK_TOKENS - MIN_TASK_TOKENS))


class BudgetAgent(Agent):
    """Recommends per-task Codex token spend.

    Two steps: scale the allocation by task difficulty, then throttle it to what
    the budget can sustain until its reset. If little is left but many days
    remain before reset, it recommends conserving.
    """

    name = "BudgetAgent"

    def recommend(self, view: BudgetView, difficulty: float) -> AgentOutcome:
        want = difficulty_tokens(difficulty)
        afford = view.remaining / max(view.days_to_reset, 1)

        if view.remaining <= 0:
            return AgentOutcome(
                agent=self.name,
                ok=False,
                summary="token budget exhausted for this period",
                issues=["budget exhausted — defer Codex-backed work until reset"],
                data={
                    "recommended_tokens": 0,
                    "mode": "exhausted",
                    "difficulty": difficulty,
                    "daily_allowance": round(afford, 1),
                },
            )

        if want <= afford:
            return AgentOutcome(
                agent=self.name,
                ok=True,
                summary=f"normal: up to {want} tokens for this task",
                data={
                    "recommended_tokens": want,
                    "mode": "normal",
                    "difficulty": difficulty,
                    "daily_allowance": round(afford, 1),
                },
            )

        recommended = max(int(afford), MIN_TASK_TOKENS // 2)
        return AgentOutcome(
            agent=self.name,
            ok=True,
            summary=(
                f"conserve: this task wants ~{want} tokens, but only ~{int(afford)}"
                f"/day is sustainable for the {view.days_to_reset} days until reset"
                f" — reducing to {recommended}"
            ),
            issues=[
                f"low budget for the {view.days_to_reset} days remaining — "
                "reduce Codex token usage per task"
            ],
            data={
                "recommended_tokens": recommended,
                "mode": "conserve",
                "difficulty": difficulty,
                "daily_allowance": round(afford, 1),
            },
        )
