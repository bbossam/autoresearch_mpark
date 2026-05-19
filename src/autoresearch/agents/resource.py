from __future__ import annotations

from dataclasses import dataclass, field

from .base import Agent, AgentOutcome


@dataclass(frozen=True)
class GpuInfo:
    index: int
    mem_total_mb: int
    mem_free_mb: int
    util_pct: int


@dataclass
class MachineState:
    """A machine's live capacity, gathered by the execution layer (remote.py)."""

    machine_id: str
    reachable: bool = True
    gpus: list[GpuInfo] = field(default_factory=list)
    disk_free_gb: float = 0.0
    note: str = ""


@dataclass(frozen=True)
class ResourceRequest:
    gpus_needed: int = 1
    min_free_gpu_mb: int = 0
    min_disk_gb: float = 0.0


class ResourceAgent(Agent):
    """Decides whether — and where — an experiment can run.

    Pure: it judges already-gathered MachineState against a ResourceRequest, so
    a run is never dispatched to a machine that is full, out of disk, or down.
    """

    name = "ResourceAgent"

    def assess(
        self, state: MachineState, request: ResourceRequest
    ) -> AgentOutcome:
        """Can this one machine satisfy the request right now?"""
        if not state.reachable:
            return AgentOutcome(
                agent=self.name,
                ok=False,
                summary=f"{state.machine_id}: unreachable",
                issues=[state.note or "machine unreachable"],
                data={"machine_id": state.machine_id, "free_gpus": []},
            )
        free = [
            g.index for g in state.gpus if g.mem_free_mb >= request.min_free_gpu_mb
        ]
        issues: list[str] = []
        if len(free) < request.gpus_needed:
            issues.append(
                f"needs {request.gpus_needed} GPU(s) with "
                f">= {request.min_free_gpu_mb} MB free; {len(free)} available"
            )
        if state.disk_free_gb < request.min_disk_gb:
            issues.append(
                f"needs {request.min_disk_gb} GB disk; "
                f"{state.disk_free_gb:.1f} GB free"
            )
        ok = not issues
        return AgentOutcome(
            agent=self.name,
            ok=ok,
            summary=f"{state.machine_id}: {'ready' if ok else 'not ready'}",
            issues=issues,
            data={
                "machine_id": state.machine_id,
                "free_gpus": free[: request.gpus_needed] if ok else free,
                "disk_free_gb": state.disk_free_gb,
            },
        )

    def place(
        self, states: list[MachineState], request: ResourceRequest
    ) -> AgentOutcome:
        """Pick the best machine across the fleet — most free GPU memory wins."""
        candidates = [
            (state, outcome)
            for state in states
            if (outcome := self.assess(state, request)).ok
        ]
        if not candidates:
            return AgentOutcome(
                agent=self.name,
                ok=False,
                summary="no machine can satisfy the request",
                issues=[f"{len(states)} machine(s) checked, none ready"],
                data={"placement": None},
            )
        best_state, best_outcome = max(
            candidates,
            key=lambda c: sum(g.mem_free_mb for g in c[0].gpus),
        )
        return AgentOutcome(
            agent=self.name,
            ok=True,
            summary=f"placed on {best_state.machine_id}",
            data={
                "placement": {
                    "machine_id": best_state.machine_id,
                    "gpu_indices": best_outcome.data["free_gpus"],
                }
            },
        )
