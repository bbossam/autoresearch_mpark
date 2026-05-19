from __future__ import annotations

from datetime import datetime, timezone

from ..models import AgentPermission, IdeaSpec, ProjectCapsule, RunContract
from .base import Agent


class PlanningAgent(Agent):
    """Turns a research idea into an executable, file-scoped RunContract.

    Pure: it returns a RunContract and never touches a target repo. The
    contract it emits is always re-checked by the ValidationAgent.
    """

    name = "PlanningAgent"

    def plan(
        self,
        idea: IdeaSpec,
        capsule: ProjectCapsule,
        run_id: str | None = None,
    ) -> RunContract:
        allowed_files = idea.allowed_files or list(capsule.allowed_files)
        if not allowed_files:
            raise ValueError(
                f"cannot plan {idea.idea_id!r}: neither the idea nor capsule "
                f"{capsule.project_id!r} declares allowed_files"
            )
        rid = run_id or f"{idea.idea_id}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
        agents = [
            AgentPermission(agent_name="PlanningAgent", may_write=False),
            AgentPermission(agent_name="ValidationAgent", may_write=False),
            AgentPermission(
                agent_name="ImplementerAgent",
                may_write=True,
                allowed_files=list(allowed_files),
            ),
            AgentPermission(agent_name="AnalysisAgent", may_write=False),
            AgentPermission(agent_name="ReviewAgent", may_write=False),
        ]
        return RunContract(
            run_id=rid,
            target_project=capsule.project_id,
            hypothesis=idea.hypothesis,
            primary_metric=idea.primary_metric,
            allowed_files=list(allowed_files),
            forbidden_files=list(capsule.forbidden_files),
            max_files_changed=idea.max_files_changed or 5,
            max_lines_changed=idea.max_lines_changed or 300,
            agents=agents,
            accept_rules=list(idea.accept_rules),
            guardrail_metrics=list(idea.guardrail_metrics),
            metadata={"idea_id": idea.idea_id},
        )
