from __future__ import annotations

from pathlib import Path

from .io import load_yaml_model
from .models import MachineCapsule, ProjectCapsule


class ProjectRegistry:
    def __init__(self, capsules: dict[str, ProjectCapsule]):
        self._capsules = capsules

    @classmethod
    def load(cls, root: str | Path = "configs/project_capsules") -> "ProjectRegistry":
        root = Path(root)
        capsules: dict[str, ProjectCapsule] = {}
        if not root.exists():
            return cls(capsules)
        for path in sorted([*root.glob("*.yaml"), *root.glob("*.yml")]):
            capsule = load_yaml_model(path, ProjectCapsule)
            capsules[capsule.project_id] = capsule
        return cls(capsules)

    def get(self, project_id: str) -> ProjectCapsule:
        try:
            return self._capsules[project_id]
        except KeyError as exc:
            known = ", ".join(sorted(self._capsules)) or "<none>"
            raise KeyError(f"unknown project_id {project_id!r}; known: {known}") from exc

    def all(self) -> list[ProjectCapsule]:
        return list(self._capsules.values())


class MachineRegistry:
    """The registry of remote servers, loaded from `configs/machines/`."""

    def __init__(self, machines: dict[str, MachineCapsule]):
        self._machines = machines

    @classmethod
    def load(cls, root: str | Path = "configs/machines") -> "MachineRegistry":
        root = Path(root)
        machines: dict[str, MachineCapsule] = {}
        if not root.exists():
            return cls(machines)
        for path in sorted([*root.glob("*.yaml"), *root.glob("*.yml")]):
            capsule = load_yaml_model(path, MachineCapsule)
            machines[capsule.machine_id] = capsule
        return cls(machines)

    def get(self, machine_id: str) -> MachineCapsule:
        try:
            return self._machines[machine_id]
        except KeyError as exc:
            known = ", ".join(sorted(self._machines)) or "<none>"
            raise KeyError(
                f"unknown machine_id {machine_id!r}; known: {known}"
            ) from exc

    def all(self) -> list[MachineCapsule]:
        return list(self._machines.values())

