from __future__ import annotations

from pathlib import Path

from ..diff_guard import audit_diff
from ..models import RunContract
from ..registry import ProjectRegistry
from .base import Agent, AgentOutcome


class ValidationAgent(Agent):
    """Read-only gatekeeper.

    Verifies that a contract is consistent with its project capsule, and that a
    target-repo diff stays inside the contract's file and size limits. It can
    only ever return yes/no plus reasons — it never mutates anything.
    """

    name = "ValidationAgent"

    def validate_contract(
        self, contract: RunContract, registry: ProjectRegistry
    ) -> AgentOutcome:
        try:
            capsule = registry.get(contract.target_project)
        except KeyError as exc:
            return AgentOutcome(
                agent=self.name,
                ok=False,
                summary="unknown target project",
                issues=[str(exc)],
            )
        issues: list[str] = []
        for pattern in contract.allowed_files:
            if pattern not in capsule.allowed_files:
                issues.append(
                    f"allowed_files entry not declared in capsule: {pattern}"
                )
            if pattern in capsule.forbidden_files:
                issues.append(
                    f"allowed_files entry is forbidden by capsule: {pattern}"
                )
        ok = not issues
        return AgentOutcome(
            agent=self.name,
            ok=ok,
            summary=(
                "contract consistent with capsule"
                if ok
                else f"{len(issues)} consistency issue(s)"
            ),
            issues=issues,
            data={"target_project": contract.target_project},
        )

    def validate_diff(
        self, contract: RunContract, repo: str | Path
    ) -> AgentOutcome:
        audit = audit_diff(contract, repo)
        return AgentOutcome(
            agent=self.name,
            ok=audit.passed,
            summary=(
                "diff within contract"
                if audit.passed
                else f"{len(audit.rejection_reasons)} diff violation(s)"
            ),
            issues=list(audit.rejection_reasons),
            data={
                "changed_files": audit.changed_files,
                "total_lines_changed": audit.total_lines_changed,
            },
        )
