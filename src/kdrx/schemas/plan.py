"""Plan-first artifacts: TaskSpec, AgentBrief, AgentResult, ResearchPlan, RunManifest."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import AgentRole, Criticality, TaskStage, TaskStatus


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_retries: int = 2
    backoff_seconds: float = 0.0
    require_alternative_agent: bool = False


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tokens: int = 0
    queries: int = 0
    wall_seconds: int = 0


class AcceptanceCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[str] = Field(default_factory=list)
    output_schema: str | None = None
    required_evidence_refs: int = 0


class TaskSpec(BaseModel):
    """A single node in the DAG (plan §15).

    The DAG compiler enforces: one mission, one owner per output, no dependent
    in the same wave, reviewer != author, minimal tool scope.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str
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


class AgentBrief(BaseModel):
    """The brief handed to an agent for exactly one task.

    Kimi contract parity (audit PR-03): o briefing autocontido é
    ``mission`` + ``guidance`` + ``context`` — mission diz o QUÊ, guidance
    diz COMO (abordagem, restrições de estilo/método) e context carrega os
    dados já coletados que o agent precisa ler antes de agir.
    """

    model_config = ConfigDict(extra="forbid")

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


class AgentResult(BaseModel):
    """The declared result of an agent for one task.

    ``outputs_produced`` must be a subset of the task's declared outputs; a
    completed result with missing outputs fails the SubagentStop gate.
    """

    model_config = ConfigDict(extra="forbid")

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


class ResearchPlan(BaseModel):
    """The full plan-first artifact (plan §14): plan.md + manifest + DAG + waves."""

    model_config = ConfigDict(extra="forbid")

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


class RunManifest(BaseModel):
    """Resumable run state (plan §31, §40 ``/kdr:resume``)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
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
