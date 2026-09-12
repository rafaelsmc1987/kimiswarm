"""Plan-first artifacts: TaskSpec, AgentBrief, AgentResult, ResearchPlan, RunManifest."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .versioning import VersionedModel, validate_component

from .enums import AgentRole, Criticality, TaskStage, TaskStatus


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(default=2, ge=0, le=20)
    backoff_seconds: float = Field(default=0.0, ge=0)
    require_alternative_agent: bool = False


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tokens: int | None = Field(default=None, ge=0)
    queries: int | None = Field(default=None, ge=0)
    wall_seconds: int | None = Field(default=None, ge=0)


class AcceptanceCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[str] = Field(default_factory=list)
    output_schema: str | None = None
    required_evidence_refs: int = Field(default=0, ge=0)


class TaskSpec(VersionedModel):
    """A single node in the DAG (plan §15).

    The DAG compiler enforces: one mission, one owner per output, no dependent
    in the same wave, reviewer != author, minimal tool scope.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str | None = None
    task_id: str
    _validate_task_id = field_validator("task_id")(validate_component)
    stage: TaskStage
    wave: int
    role: AgentRole
    mission: str
    dependencies: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    read_only: bool = True
    source_policy: str | None = None
    acceptance: AcceptanceCriteria = Field(default_factory=AcceptanceCriteria)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    budget: Budget = Field(default_factory=Budget)
    criticality: Criticality = Criticality.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    owner: str | None = None
    reviewer: str | None = None
    guidance: str = ""  # propagado ao AgentBrief (Kimi contract)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentBrief(VersionedModel):
    """The brief handed to an agent for exactly one task.

    Kimi contract parity (audit PR-03): o briefing autocontido é
    ``mission`` + ``guidance`` + ``context`` — mission diz o QUÊ, guidance
    diz COMO (abordagem, restrições de estilo/método) e context carrega os
    dados já coletados que o agent precisa ler antes de agir.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None
    plan_id: str | None = None
    plan_revision: int = Field(default=0, ge=0)
    attempt_id: str | None = None
    kind: str | None = None
    budget: Budget = Field(default_factory=Budget)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    brief_id: str
    task_id: str
    role: AgentRole
    mission: str
    guidance: str = ""
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    read_only: bool = True
    source_policy: str | None = None
    acceptance: AcceptanceCriteria = Field(default_factory=AcceptanceCriteria)
    context: dict[str, Any] = Field(default_factory=dict)


class AgentResult(VersionedModel):
    """The declared result of an agent for one task.

    ``outputs_produced`` must be a subset of the task's declared outputs; a
    completed result with missing outputs fails the SubagentStop gate.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None
    plan_id: str | None = None
    plan_revision: int = Field(default=0, ge=0)
    attempt_id: str | None = None
    result_id: str
    task_id: str
    agent_role: AgentRole
    outputs_produced: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    declared_tests: list[str] = Field(default_factory=list)
    executed_tests: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    finished_at: datetime | None = None

    def covers_outputs(self, expected: list[str]) -> bool:
        return set(expected).issubset(set(self.outputs_produced))

    def tests_actually_executed(self) -> bool:
        return set(self.executed_tests) >= set(self.declared_tests)


class OwnershipEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: str
    owner_task_id: str
    owner_role: AgentRole


class PlannerDisposition(BaseModel):
    """Disposition of one planner recommendation (council import, D5).

    Every planner recommendation must resolve to an explicit disposition so
    the handoff is machine-checkable; the canonical artifact is
    ``planner-dispositions.json`` (the human-readable summary lives in
    ``plan_md``).
    """

    model_config = ConfigDict(extra="forbid")

    recommendation: str
    perspective: str
    disposition: Literal["accepted", "rejected", "deferred"]
    rationale: str


class ResearchPlan(VersionedModel):
    """The full plan-first artifact (plan §14): plan.md + manifest + DAG + waves."""

    model_config = ConfigDict(extra="forbid")

    execution_backend: Literal["offline", "codex", "claude-code"] = "offline"
    plan_revision: int = Field(default=0, ge=0)
    plan_id: str
    contract_id: str
    route: str
    plan_md: str = ""
    tasks: list[TaskSpec] = Field(default_factory=list)
    waves: dict[int, list[str]] = Field(default_factory=dict)
    ownership: list[OwnershipEntry] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    acceptance_matrix: dict[str, list[str]] = Field(default_factory=dict)
    created_at: datetime | None = None

    def task_by_id(self, task_id: str) -> TaskSpec | None:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None


class PlanPatch(VersionedModel):
    """Explicit CAS revision request; budgets grant no provider credentials."""

    base_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=4000)
    add_tasks: list[TaskSpec] = Field(default_factory=list)
    remove_tasks: list[str] = Field(default_factory=list)
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    task_budgets: dict[str, Budget] = Field(default_factory=dict)
    required_budget: Budget = Field(default_factory=Budget)
    invalidate_tasks: list[str] = Field(default_factory=list)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("patch reason must not be blank")
        return value.strip()


class RunManifest(VersionedModel):
    """Resumable run state (plan §31, §40 ``/kdr:resume``)."""

    model_config = ConfigDict(extra="forbid")

    state_revision: int = Field(default=0, ge=0)
    run_id: str
    _validate_run_id = field_validator("run_id")(validate_component)
    plan_revision: int = Field(default=0, ge=0)
    plan_id: str
    contract_id: str
    route: str
    root_dir: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    status: TaskStatus = TaskStatus.PENDING
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    completed_tasks: list[str] = Field(default_factory=list)
    failed_tasks: list[str] = Field(default_factory=list)
    gate_results: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
