from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DEFAULT_FORBIDDEN_FILES = [
    "eval/**",
    "evaluation/**",
    "datasets/**",
    "data/**",
    "benchmarks/**",
    "shared/**",
    "common/**",
]


class MetricOperator(str, Enum):
    lt = "lt"
    lte = "lte"
    gt = "gt"
    gte = "gte"
    eq = "eq"


class AgentPermission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    may_write: bool = False
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_files: list[str] = Field(default_factory=list)


class AcceptRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    operator: MetricOperator
    threshold: float
    required: bool = True


class GuardrailMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    operator: MetricOperator
    threshold: float
    required: bool = True


class ProjectCapsule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    name: str
    description: str = ""
    repo_path: str | None = None
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=lambda: list(DEFAULT_FORBIDDEN_FILES))
    default_branch: str | None = None
    notes: str = ""

    @field_validator("project_id", "name")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class RunContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    target_project: str
    hypothesis: str
    primary_metric: str
    allowed_files: list[str]
    forbidden_files: list[str] = Field(default_factory=lambda: list(DEFAULT_FORBIDDEN_FILES))
    max_files_changed: int = 5
    max_lines_changed: int = 300
    agents: list[AgentPermission] = Field(default_factory=list)
    accept_rules: list[AcceptRule] = Field(default_factory=list)
    guardrail_metrics: list[GuardrailMetric] = Field(default_factory=list)
    log_dir: str = "experiments/logs"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("run_id", "target_project", "hypothesis", "primary_metric")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("allowed_files")
    @classmethod
    def _allowed_files_required(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("allowed_files must list at least one path or glob")
        return value

    @field_validator("max_files_changed", "max_lines_changed")
    @classmethod
    def _positive_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be >= 1")
        return value

    @model_validator(mode="after")
    def _only_implementer_may_write(self) -> "RunContract":
        writers = [agent.agent_name for agent in self.agents if agent.may_write]
        invalid = [name for name in writers if name != "ImplementerAgent"]
        if invalid:
            raise ValueError(
                "Only ImplementerAgent may have may_write=true; invalid writers: "
                + ", ".join(invalid)
            )
        return self


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    target_project: str
    status: Literal["accepted", "rejected", "dry_run"]
    accepted: bool = False
    modified_files: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    rejection_reasons: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IdeaSpec(BaseModel):
    """A research idea — the upstream input the PlanningAgent turns into a RunContract.

    Loaded from an `ideas/*.md` file (YAML frontmatter + free-form notes) or a
    plain YAML file.
    """

    model_config = ConfigDict(extra="forbid")

    idea_id: str
    target_project: str
    hypothesis: str
    primary_metric: str
    allowed_files: list[str] = Field(default_factory=list)
    accept_rules: list[AcceptRule] = Field(default_factory=list)
    guardrail_metrics: list[GuardrailMetric] = Field(default_factory=list)
    max_files_changed: int | None = None
    max_lines_changed: int | None = None
    notes: str = ""

    @field_validator("idea_id", "target_project", "hypothesis", "primary_metric")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class ExperimentStatus(BaseModel):
    """Heartbeat record written by the watchdog — the liveness signal that lets
    agents and humans watch long, unattended experiment runs.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    state: Literal["running", "completed", "failed", "timeout", "stalled"]
    command: str
    pid: int | None = None
    started_at: datetime
    updated_at: datetime
    elapsed_seconds: float
    last_output_age_seconds: float
    exit_code: int | None = None
    time_budget_seconds: float
    stall_timeout_seconds: float
    note: str = ""


class EnvKind(str, Enum):
    docker = "docker"
    conda = "conda"


class EnvSpec(BaseModel):
    """How a machine isolates an experiment — a Docker image or a conda env."""

    model_config = ConfigDict(extra="forbid")

    kind: EnvKind
    image: str | None = None       # docker image reference
    conda_env: str | None = None   # conda environment name
    spec_file: str | None = None   # Dockerfile or environment.yml, for rebuilds

    @model_validator(mode="after")
    def _require_target(self) -> "EnvSpec":
        if self.kind == EnvKind.docker and not self.image:
            raise ValueError("docker env requires 'image'")
        if self.kind == EnvKind.conda and not self.conda_env:
            raise ValueError("conda env requires 'conda_env'")
        return self


class MachineCapsule(BaseModel):
    """A registered server: where it is, what it has, and how to run on it."""

    model_config = ConfigDict(extra="forbid")

    machine_id: str
    name: str
    ssh_target: str = ""  # user@host; empty means the local machine
    scheduler: Literal["slurm", "ssh"] = "slurm"
    gpus: int = 0
    workdir: str = "."
    data_dirs: list[str] = Field(default_factory=list)
    env: EnvSpec
    notes: str = ""

    @field_validator("machine_id", "name")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

