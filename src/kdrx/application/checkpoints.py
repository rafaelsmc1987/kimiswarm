"""Typed, referentially checked evidence snapshots and committed task receipts."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from kdrx.application.artifacts import load_jsonl
from kdrx.evidence.documents import DocumentIR
from kdrx.runtime.blobs import BlobStore
from kdrx.schemas.claims import Claim, ClaimEvidenceEdge
from kdrx.schemas.corpus import SourceRecord, EvidenceSpan
from kdrx.schemas.enums import Standing
from kdrx.state import RunState, hash_bytes


class StandingSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    claim_id: str
    standing: Standing
    confidence: float = Field(ge=0, le=1)
    components: dict[str, float] = Field(default_factory=dict)
    calibration_basis: str


@dataclass(frozen=True)
class EvidenceCheckpoint:
    sources: list[SourceRecord]
    spans: list[EvidenceSpan]
    claims: list[Claim]
    standings: list[StandingSnapshot]
    edges: list[ClaimEvidenceEdge]
    report: str


def _index(records, key):
    indexed = {getattr(record, key): record for record in records}
    if len(indexed) != len(records):
        raise ValueError(f"duplicate {key} in checkpoint")
    return indexed


def load_checkpoint(state: RunState) -> EvidenceCheckpoint:
    sources = load_jsonl(state._resolve("corpus/sources.jsonl"), SourceRecord)
    spans = load_jsonl(state._resolve("evidence/spans.jsonl"), EvidenceSpan)
    claims = load_jsonl(state._resolve("claims/claims.jsonl"), Claim)
    standings = load_jsonl(state._resolve("claims/standings.jsonl"), StandingSnapshot)
    edges = load_jsonl(state._resolve("claims/edges.jsonl"), ClaimEvidenceEdge)
    source_index = _index(sources, "source_id")
    span_index = _index(spans, "evidence_id")
    claim_index = _index(claims, "claim_id")
    standing_index = _index(standings, "claim_id")
    _index(edges, "edge_id")
    if set(standing_index) != set(claim_index):
        raise ValueError("standing/claim checkpoint identity mismatch")
    blobs = BlobStore(state.root / ".blobs")
    texts = {}
    for source in sources:
        ir = DocumentIR.model_validate(source.metadata.get("document_ir"))
        text = blobs.get(ir.extracted_text_hash).decode("utf-8")
        blobs.get(ir.raw_bytes_hash)
        if (
            not ir.verify()
            or text != ir.text
            or ir.source_id != source.source_id
            or source.content_hash != f"sha256:{ir.extracted_text_hash}"
        ):
            raise ValueError("source snapshot checkpoint mismatch")
        texts[source.source_id] = text
    for span in spans:
        start, end = span.locator.char_start, span.locator.char_end
        text = texts.get(span.source_id, "")
        if (
            span.source_id not in source_index
            or start is None
            or end is None
            or not 0 <= start < end <= len(text)
            or text[start:end] != span.verbatim_span
        ):
            raise ValueError("evidence span checkpoint mismatch")
    for claim in claims:
        if set(claim.support_edges + claim.contradiction_edges) - set(span_index):
            raise ValueError("claim has unresolved evidence references")
        if set(claim.dependencies) - set(claim_index):
            raise ValueError("claim has unresolved dependencies")
        standing = standing_index[claim.claim_id]
        if (
            standing.standing != claim.standing
            or abs(standing.confidence - claim.confidence) > 0.0001
        ):
            raise ValueError("claim/standing checkpoint mismatch")
    for edge in edges:
        if edge.claim_id not in claim_index or edge.evidence_id not in span_index:
            raise ValueError("edge has unresolved checkpoint references")
    report = ""
    for relative in ("delivery/report.md", "delivery/draft.md"):
        path = state._resolve(relative)
        if path.is_file():
            report = path.read_text(encoding="utf-8")
            break
    return EvidenceCheckpoint(sources, spans, claims, standings, edges, report)


def validate_task_receipts(state, plan, manifest, precompleted) -> None:
    from kdrx.runtime.plan_revisions import receipt_plan_matches

    committed = state.store.completed(state.run_id)
    if set(committed) != set(precompleted):
        raise ValueError("task checkpoint disagrees with committed database results")
    plan_hash = hash_bytes(state._resolve("plan.json").read_bytes())
    if manifest.metadata.get("plan", {}).get("sha256") != plan_hash:
        raise ValueError("checkpoint plan hash mismatch")
    for task_id, result in precompleted.items():
        if (
            result.model_dump(mode="json") != committed[task_id]
            or result.run_id != state.run_id
            or result.plan_id != plan.plan_id
        ):
            raise ValueError(f"committed result identity mismatch: {task_id}")
        checkpoint = manifest.metadata["task_commits"][task_id]
        if not receipt_plan_matches(state, plan, committed[task_id], checkpoint):
            raise ValueError(f"task input plan changed: {task_id}")
        for relative, digest in checkpoint.get("input_hashes", {}).items():
            if relative == "plan.json" and result.plan_revision != plan.plan_revision:
                if digest != checkpoint["plan_hash"]:
                    raise ValueError(f"task input plan hash mismatch: {task_id}")
                continue  # exact archived plan and unchanged TaskSpec checked above
            if hash_bytes(state._resolve(relative).read_bytes()) != digest:
                raise ValueError(f"task input changed: {task_id}/{relative}")
        artifacts = state.store.artifacts(state.run_id, task_id)
        if {a["path"] for a in artifacts} != set(plan.task_by_id(task_id).outputs):
            raise ValueError(f"incomplete committed artifacts: {task_id}")
        for artifact in artifacts:
            data = state._resolve(artifact["path"]).read_bytes()
            if (
                hash_bytes(data) != artifact["hash"]
                or len(data) != artifact["size"]
                or artifact["attempt_id"] != result.attempt_id
            ):
                raise ValueError(f"committed artifact mismatch: {artifact['path']}")
