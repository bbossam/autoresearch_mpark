from __future__ import annotations

from autoresearch.agents import (
    AnalysisAgent,
    ImplementationAgent,
    PlanningAgent,
    ValidationAgent,
)
from autoresearch.leaderboard import Leaderboard
from autoresearch.models import (
    AcceptRule,
    IdeaSpec,
    MetricOperator,
    ProjectCapsule,
    RunContract,
    RunResult,
)
from autoresearch.registry import ProjectRegistry


def _capsule() -> ProjectCapsule:
    return ProjectCapsule(
        project_id="p1", name="P1", allowed_files=["src/exp/**"]
    )


def _idea() -> IdeaSpec:
    return IdeaSpec(
        idea_id="speedup",
        target_project="p1",
        hypothesis="caching helps",
        primary_metric="score",
        accept_rules=[
            AcceptRule(metric="score", operator=MetricOperator.gt, threshold=0.5)
        ],
    )


def _result(score: float) -> RunResult:
    return RunResult(
        run_id="r1", target_project="p1", status="dry_run", metrics={"score": score}
    )


def test_planning_agent_builds_valid_contract():
    contract = PlanningAgent().plan(_idea(), _capsule(), run_id="r1")

    assert isinstance(contract, RunContract)
    assert contract.run_id == "r1"
    assert contract.target_project == "p1"
    assert contract.allowed_files == ["src/exp/**"]
    writers = [a.agent_name for a in contract.agents if a.may_write]
    assert writers == ["ImplementerAgent"]


def test_validation_agent_detects_unknown_project():
    contract = PlanningAgent().plan(_idea(), _capsule(), run_id="r1")
    outcome = ValidationAgent().validate_contract(contract, ProjectRegistry({}))

    assert not outcome.ok
    assert outcome.issues


def test_validation_agent_accepts_consistent_contract():
    capsule = _capsule()
    contract = PlanningAgent().plan(_idea(), capsule, run_id="r1")
    registry = ProjectRegistry({"p1": capsule})

    outcome = ValidationAgent().validate_contract(contract, registry)

    assert outcome.ok, outcome.issues


def test_implementation_agent_makes_no_writes():
    contract = PlanningAgent().plan(_idea(), _capsule(), run_id="r1")
    outcome = ImplementationAgent().apply(contract)

    assert outcome.ok
    assert outcome.data["modified_files"] == []


def test_analysis_agent_accepts_passing_metrics():
    contract = PlanningAgent().plan(_idea(), _capsule(), run_id="r1")
    outcome = AnalysisAgent().analyze(contract, _result(0.9))

    assert outcome.ok
    assert outcome.data["accepted"]


def test_analysis_agent_rejects_failing_metrics():
    contract = PlanningAgent().plan(_idea(), _capsule(), run_id="r1")
    outcome = AnalysisAgent().analyze(contract, _result(0.1))

    assert not outcome.ok
    assert outcome.issues


def test_analysis_agent_reports_beating_the_best():
    contract = PlanningAgent().plan(_idea(), _capsule(), run_id="r1")
    outcome = AnalysisAgent().analyze(contract, _result(0.9), prior_best=0.7)

    assert outcome.data["beats_best"] is True


def test_analysis_agent_rejects_non_improvement():
    # 0.6 passes the accept rule (> 0.5) but does NOT beat the best (0.8)
    contract = PlanningAgent().plan(_idea(), _capsule(), run_id="r1")
    outcome = AnalysisAgent().analyze(contract, _result(0.6), prior_best=0.8)

    assert not outcome.ok
    assert outcome.data["beats_best"] is False


def test_leaderboard_records_best(tmp_path):
    board = Leaderboard(tmp_path / "lb.json")

    assert board.record("p1", "score", 0.5, "r1", higher_is_better=True)
    assert not board.record("p1", "score", 0.4, "r2", higher_is_better=True)
    assert board.record("p1", "score", 0.6, "r3", higher_is_better=True)
    assert board.best("p1", "score")["run_id"] == "r3"
