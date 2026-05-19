"""Role-specific agents — one file per agent, one stage of the pipeline each.

Pipeline: ResearchAgent -> PlanningAgent -> ValidationAgent ->
ImplementationAgent -> ValidationAgent -> AnalysisAgent -> ReviewAgent.
ContextAgent (boot recall) and ResourceAgent (machine placement) are
session/infrastructure level. See AGENTS.md.
"""

from .analyst import AnalysisAgent
from .base import Agent, AgentOutcome
from .budget import BudgetAgent, BudgetView, estimate_difficulty
from .context import ContextAgent, SessionSnapshot
from .implementer import ImplementationAgent
from .planner import PlanningAgent
from .researcher import ResearchAgent, ResearchContext
from .resource import MachineState, ResourceAgent, ResourceRequest
from .reviewer import ReviewAgent, ReviewArtifacts
from .validator import ValidationAgent

__all__ = [
    "Agent",
    "AgentOutcome",
    "ResearchAgent",
    "ResearchContext",
    "PlanningAgent",
    "ValidationAgent",
    "ImplementationAgent",
    "AnalysisAgent",
    "ReviewAgent",
    "ReviewArtifacts",
    "ContextAgent",
    "SessionSnapshot",
    "ResourceAgent",
    "ResourceRequest",
    "MachineState",
    "BudgetAgent",
    "BudgetView",
    "estimate_difficulty",
]
