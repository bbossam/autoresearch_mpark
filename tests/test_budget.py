from __future__ import annotations

from datetime import date

from autoresearch.agents import BudgetAgent, BudgetView
from autoresearch.agents.budget import estimate_difficulty
from autoresearch.budget import TokenBudget
from autoresearch.models import AcceptRule, MetricOperator, RunContract, TokenBudgetConfig


def _config(**kw) -> TokenBudgetConfig:
    base = dict(total_tokens=100000, period_days=30, period_start=date(2026, 5, 1))
    base.update(kw)
    return TokenBudgetConfig(**base)


def test_budget_records_and_persists(tmp_path):
    ledger = tmp_path / "budget.json"
    budget = TokenBudget(_config(), ledger, today=date(2026, 5, 10))
    assert budget.remaining() == 100000
    budget.record(30000)
    budget.save()

    reloaded = TokenBudget(_config(), ledger, today=date(2026, 5, 10))
    assert reloaded.remaining() == 70000


def test_budget_rolls_over_after_the_period(tmp_path):
    ledger = tmp_path / "budget.json"
    budget = TokenBudget(_config(), ledger, today=date(2026, 5, 10))
    budget.record(50000)
    budget.save()

    later = TokenBudget(_config(), ledger, today=date(2026, 6, 15))
    assert later.consumed == 0
    assert later.remaining() == 100000


def test_budget_agent_normal_mode():
    view = BudgetView(total=100000, consumed=0, remaining=100000, days_to_reset=2)
    outcome = BudgetAgent().recommend(view, difficulty=0.2)
    assert outcome.data["mode"] == "normal"


def test_budget_agent_recommends_conserving_when_low_and_far_from_reset():
    view = BudgetView(total=100000, consumed=99000, remaining=1000, days_to_reset=25)
    outcome = BudgetAgent().recommend(view, difficulty=0.9)
    assert outcome.data["mode"] == "conserve"
    assert outcome.issues


def test_budget_agent_exhausted():
    view = BudgetView(total=100000, consumed=100000, remaining=0, days_to_reset=10)
    outcome = BudgetAgent().recommend(view, difficulty=0.5)
    assert not outcome.ok
    assert outcome.data["mode"] == "exhausted"


def test_estimate_difficulty_orders_tasks():
    easy = RunContract(
        run_id="e", target_project="p", hypothesis="x", primary_metric="m",
        allowed_files=["a.py"], max_files_changed=1, max_lines_changed=10,
    )
    hard = RunContract(
        run_id="h", target_project="p", hypothesis="y" * 400, primary_metric="m",
        allowed_files=[f"d{i}/**" for i in range(10)],
        max_files_changed=20, max_lines_changed=1000,
        accept_rules=[AcceptRule(metric="m", operator=MetricOperator.gt, threshold=0)],
    )
    assert estimate_difficulty(hard) > estimate_difficulty(easy)
