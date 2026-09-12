"""Explicit executor capabilities; task identity never selects a fixture fallback."""

from __future__ import annotations

from dataclasses import dataclass


_LEGACY_KINDS = {
    "T-RETRIEVE": "retrieval",
    "T-VERIFY": "source_verification",
    "T-SYNTHESIZE": "synthesis",
    "T-INTEGRITY": "integrity",
}


def capability_key(task) -> str | None:
    return task.kind or _LEGACY_KINDS.get(task.task_id)


@dataclass(frozen=True)
class ExecutorCapability:
    kind: str
    method: str | None
    model_required: bool = False
    unavailable_reason: str | None = None


class ExecutorRegistry:
    def __init__(self):
        self._entries: dict[str, ExecutorCapability] = {}

    def register(self, capability: ExecutorCapability) -> None:
        if capability.kind in self._entries:
            raise ValueError(f"duplicate executor capability: {capability.kind}")
        self._entries[capability.kind] = capability

    def get(self, kind: str | None) -> ExecutorCapability:
        entry = self._entries.get(kind)
        if entry is None:
            supported = ", ".join(
                sorted(
                    k
                    for k, value in self._entries.items()
                    if not value.unavailable_reason
                )
            )
            raise ValueError(
                f"unavailable capability {kind!r}; set task.kind to an implemented capability: {supported}"
            )
        if entry.unavailable_reason:
            raise ValueError(
                f"unavailable capability {kind!r}: {entry.unavailable_reason}"
            )
        return entry

    def issues(self, plan) -> list[str]:
        errors = []
        for task in plan.tasks:
            try:
                entry = self.get(capability_key(task))
                if entry.model_required and plan.execution_backend == "offline":
                    raise ValueError(
                        "model capability requires an explicit codex or claude-code plan"
                    )
            except ValueError as exc:
                errors.append(f"{task.task_id}: {exc}")
        return errors

    def execute(self, context, brief):
        entry = self.get(capability_key(brief))
        if entry.model_required or not entry.method:
            raise ValueError("model capability must use its explicit CLI backend")
        return getattr(context, entry.method)(brief)


EXECUTORS = ExecutorRegistry()
for _kind, _method in {
    "retrieval": "_retrieve",
    "source_verification": "_verify",
    "synthesis": "_synthesize",
    "writing": "_synthesize",
    "integrity": "_integrity",
    "deterministic_gate": "_integrity",
    "claim_analysis": "_analyze_claims",
    "artifact_export": "_export_evidence",
}.items():
    EXECUTORS.register(ExecutorCapability(_kind, _method))
for _kind in ("model_analysis", "model_writer", "model_review"):
    EXECUTORS.register(ExecutorCapability(_kind, None, model_required=True))
EXECUTORS.register(
    ExecutorCapability(
        "code",
        None,
        unavailable_reason="OS process sandbox is not configured; submit a research-only plan or configure a validated code backend",
    )
)
