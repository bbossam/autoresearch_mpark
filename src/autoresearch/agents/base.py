from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentOutcome:
    """Uniform result returned by an agent's primary action.

    Agents are pure decision-makers: they return an AgentOutcome and never
    perform file or process I/O. The CLI and watchdog are the execution layer.
    """

    agent: str
    ok: bool
    summary: str
    issues: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


class Agent:
    """Marker base class. Each agent owns exactly one stage of the pipeline."""

    name: str = "Agent"
