"""Token-consumption budget with periodic reset, backed by a JSON ledger.

The config (total allowance + reset cadence) is user-owned YAML; consumption is
tracked in a separate ledger file so the system never overwrites the user's
settings. Used to pace Codex spend across a multi-day reset cycle.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .io import load_yaml_model
from .models import TokenBudgetConfig


class TokenBudget:
    """Live token budget: config + consumption ledger, with period rollover."""

    def __init__(
        self,
        config: TokenBudgetConfig,
        ledger_path: str | Path = "experiments/token_budget.json",
        today: date | None = None,
    ):
        self.config = config
        self.ledger_path = Path(ledger_path)
        self.today = today or date.today()
        self.period_start = config.period_start
        self.consumed = 0
        if self.ledger_path.exists():
            data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            self.period_start = date.fromisoformat(data["period_start"])
            self.consumed = int(data.get("consumed", 0))
        self._roll_over()

    def _roll_over(self) -> None:
        """Advance the period (zeroing consumption) until it contains today."""
        span = timedelta(days=self.config.period_days)
        while self.today >= self.period_start + span:
            self.period_start += span
            self.consumed = 0

    def remaining(self) -> int:
        return max(self.config.total_tokens - self.consumed, 0)

    def days_to_reset(self) -> int:
        end = self.period_start + timedelta(days=self.config.period_days)
        return max((end - self.today).days, 1)

    def daily_allowance(self) -> float:
        """Tokens per remaining day that the budget can still sustain."""
        return self.remaining() / self.days_to_reset()

    def record(self, tokens: int) -> None:
        self.consumed += max(tokens, 0)

    def save(self) -> Path:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(
            json.dumps(
                {"period_start": self.period_start.isoformat(), "consumed": self.consumed},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return self.ledger_path


def load_budget_config(path: str | Path) -> TokenBudgetConfig | None:
    """Load the budget config, or None if the file is absent (feature off)."""
    path = Path(path)
    if not path.exists():
        return None
    return load_yaml_model(path, TokenBudgetConfig)
