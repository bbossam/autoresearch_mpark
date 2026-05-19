from pathlib import Path

from autoresearch.io import load_yaml_model
from autoresearch.models import ProjectCapsule, RunContract


ROOT = Path(__file__).resolve().parents[1]


def test_valid_project_capsule():
    capsule = load_yaml_model(
        ROOT / "configs" / "project_capsules" / "example.yaml",
        ProjectCapsule,
    )

    assert capsule.project_id == "example_project"
    assert "eval/**" in capsule.forbidden_files


def test_valid_run_contract():
    contract = load_yaml_model(
        ROOT / "experiments" / "contracts" / "example_run.yaml",
        RunContract,
    )

    assert contract.run_id == "example_run_001"
    assert contract.target_project == "example_project"
    assert contract.primary_metric == "validation_score"
    assert [a.agent_name for a in contract.agents if a.may_write] == ["ImplementerAgent"]

