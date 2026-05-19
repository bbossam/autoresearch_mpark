from __future__ import annotations

from ..models import RunContract
from .base import Agent, AgentOutcome


class ImplementationAgent(Agent):
    """The only agent permitted to write into a target repo.

    Intentionally a stub in v0: it performs no writes. This keeps the control
    plane safe while the surrounding pipeline — planning, validation, analysis,
    and the watchdog — is exercised end to end.

    The class ``name`` is ``ImplementerAgent`` so that a contract granting it
    ``may_write=true`` passes RunContract's writer-permission validation.
    """

    name = "ImplementerAgent"

    def apply(self, contract: RunContract) -> AgentOutcome:
        return AgentOutcome(
            agent=self.name,
            ok=True,
            summary="stub: planning only — no target files were modified",
            data={
                "allowed_files": list(contract.allowed_files),
                "modified_files": [],
            },
        )
