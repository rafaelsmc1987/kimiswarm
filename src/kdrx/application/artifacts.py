"""Kernel-observed artifact validation and typed checkpoint loading."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from kdrx.scheduler import ExecutorError
from kdrx.schemas import SCHEMAS
from kdrx.schemas.plan import AgentResult, TaskSpec
from kdrx.state import RunState, hash_bytes


def load_jsonl(path: Path, model: type, *, required: bool = True) -> list:
    if not path.exists() and not required:
        return []
    records = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                records.append(model.model_validate_json(line))
            except ValueError as exc:
                raise ValueError(f"corrupt {path.name} at line {line_no}") from exc
    return records


def validate_outputs(
    state: RunState, task: TaskSpec, outcome: AgentResult
) -> list[dict]:
    records = []
    for rel in task.outputs:
        path = state._resolve(rel)
        if not path.is_file():
            raise ExecutorError(f"missing output: {rel}")
        data = path.read_bytes()
        if not data.strip() and path.suffix != ".jsonl":
            raise ExecutorError(f"empty output: {rel}")
        try:
            if path.suffix == ".json":
                parsed = json.loads(data)
                schema = SCHEMAS.get(task.acceptance.output_schema or "")
                if schema:
                    schema.model_validate(parsed)
            elif path.suffix == ".jsonl":
                for line in data.decode("utf-8").splitlines():
                    if line.strip():
                        json.loads(line)
        except ValueError as exc:
            raise ExecutorError(f"invalid output schema: {rel}") from exc
        records.append(
            {
                "path": rel,
                "sha256": hash_bytes(data),
                "size": len(data),
                "mime": mimetypes.guess_type(rel)[0] or "application/octet-stream",
                "producer": task.task_id,
                "attempt_id": outcome.attempt_id,
            }
        )
    refs = set()
    for rel, key in (
        ("corpus/sources.jsonl", "source_id"),
        ("evidence/spans.jsonl", "evidence_id"),
        ("claims/claims.jsonl", "claim_id"),
    ):
        for line in state.read_text(rel).splitlines():
            if line.strip():
                refs.add(json.loads(line)[key])
    if set(outcome.evidence_refs) - refs:
        raise ExecutorError("unresolved evidence references")
    if outcome.declared_tests or outcome.executed_tests:
        raise ExecutorError("agent-declared tests are not kernel execution receipts")
    return records
