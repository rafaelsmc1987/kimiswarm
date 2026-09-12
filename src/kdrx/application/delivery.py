"""One delivery policy, evaluated against a single captured set of bytes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kdrx.dag import compile_dag
from kdrx.reporting import citation_integrity_gate
from kdrx.schemas.claims import Claim
from kdrx.schemas.corpus import EvidenceSpan, SourceRecord
from kdrx.schemas.plan import ResearchPlan
from kdrx.security import security_gate
from kdrx.state import RunState, hash_bytes, hash_file
from kdrx.verification import source_trust_gate

POLICY_VERSION = "delivery/0.3"


@dataclass(frozen=True)
class DeliveryCheck:
    report_bytes: bytes
    report_hash: str
    plan_hash: str
    graph_hash: str
    gate_results: dict[str, str]
    blocking_reasons: tuple[str, ...]
    unresolved_critical: tuple[str, ...]
    input_hashes: dict[str, str]

    @property
    def deliverable(self) -> bool:
        return not self.blocking_reasons

    def as_dict(self) -> dict:
        return {
            "verdict": "pass" if self.deliverable else "fail",
            "deliverable": self.deliverable,
            "policy_version": POLICY_VERSION,
            "verified_report_hash": self.report_hash,
            "gate_results": self.gate_results,
            "blocking_reasons": list(self.blocking_reasons),
            **self.gate_results,
        }


def verify_snapshot(state: RunState) -> DeliveryCheck:
    manifest = state.load_manifest()
    rels = (
        "plan.json",
        "corpus/sources.jsonl",
        "evidence/spans.jsonl",
        "claims/claims.jsonl",
        "delivery/report.md",
    )
    captured = {rel: state._resolve(rel).read_bytes() for rel in rels}
    plan = ResearchPlan.model_validate_json(captured["plan.json"])
    sources = [
        SourceRecord.model_validate_json(line)
        for line in captured["corpus/sources.jsonl"].splitlines()
        if line.strip()
    ]
    spans = [
        EvidenceSpan.model_validate_json(line)
        for line in captured["evidence/spans.jsonl"].splitlines()
        if line.strip()
    ]
    claims = [
        Claim.model_validate_json(line)
        for line in captured["claims/claims.jsonl"].splitlines()
        if line.strip()
    ]
    report = captured["delivery/report.md"].decode("utf-8")
    plan_hash = hash_bytes(captured["plan.json"])
    dag_ok = compile_dag(plan.tasks).is_valid
    identity_ok = (
        plan.plan_id == manifest.plan_id and plan.contract_id == manifest.contract_id
    )
    saved_hash = manifest.metadata.get("plan", {}).get("sha256")
    plan_ok = dag_ok and identity_ok and (not saved_hash or saved_hash == plan_hash)
    src_ok = bool(sources) and all(
        source_trust_gate(s).verdict == "pass" for s in sources
    )
    citation = citation_integrity_gate(
        report, sources=sources, claims=claims, spans=spans
    )
    security = security_gate(state.run_dir)
    critical = tuple(
        c.claim_id
        for c in claims
        if c.importance == "critical" and c.standing == "unresolved"
    )
    reasons = []
    if manifest.status == "cancelled":
        reasons.append("run_cancelled: delivery is revoked")
    from kdrx.application.checkpoints import load_checkpoint

    checkpoint_ok = True
    try:
        load_checkpoint(state)
    except (ValueError, OSError):
        checkpoint_ok = False
        reasons.append(
            "checkpoint_integrity: typed evidence graph is invalid or incomplete"
        )
    completed = state.store.completed(state.run_id)
    from kdrx.runtime.plan_revisions import receipt_plan_matches

    tasks_ok = bool(plan.tasks) and all(
        task.task_id in completed
        and receipt_plan_matches(
            state,
            plan,
            completed[task.task_id],
            manifest.metadata.get("task_commits", {}).get(task.task_id, {}),
        )
        for task in plan.tasks
    )
    if not tasks_ok:
        reasons.append(
            "task_commits: mandatory tasks lack kernel-verified results for this plan"
        )
    from kdrx.evidence.documents import DocumentIR
    from kdrx.runtime.blobs import BlobStore

    blobs = BlobStore(state.root / ".blobs")
    texts = {}
    provenance_ok = True
    for source in sources:
        try:
            ir = DocumentIR.model_validate(source.metadata.get("document_ir"))
            raw = blobs.get(ir.raw_bytes_hash)
            text = blobs.get(ir.extracted_text_hash).decode("utf-8")
            if (
                not raw
                or not ir.verify()
                or text != ir.text
                or ir.source_id != source.source_id
                or source.content_hash != f"sha256:{ir.extracted_text_hash}"
            ):
                raise ValueError("source snapshot mismatch")
            texts[source.source_id] = text
        except (ValueError, OSError):
            provenance_ok = False
    for span in spans:
        start, end = span.locator.char_start, span.locator.char_end
        text = texts.get(span.source_id, "")
        if (
            start is None
            or end is None
            or not 0 <= start < end <= len(text)
            or text[start:end] != span.verbatim_span
        ):
            provenance_ok = False
    if not provenance_ok:
        reasons.append(
            "evidence_provenance: source snapshot or exact span does not match"
        )
    if not src_ok:
        reasons.append("source_trust: sources are missing or unverified")
    if not plan_ok:
        reasons.append("plan_dag: plan identity/hash or DAG invalid")
    reasons.extend(citation.blocking_reasons)
    if citation.verdict != "pass" and not citation.blocking_reasons:
        reasons.append("citation_integrity: unresolved advisory findings")
    reasons.extend(security.blocking_reasons)
    if critical:
        reasons.append("critical_resolved: " + ", ".join(critical))
    gates = {
        "checkpoint_integrity": "pass" if checkpoint_ok else "fail",
        "source_trust": "pass" if src_ok else "fail",
        "plan_dag": "pass" if plan_ok else "fail",
        "task_commits": "pass" if tasks_ok else "fail",
        "evidence_provenance": "pass" if provenance_ok else "fail",
        "citation_integrity": str(citation.verdict.value),
        "security": str(security.verdict.value),
        "critical_resolved": "fail" if critical else "pass",
    }
    hashes = {rel: hash_bytes(data) for rel, data in captured.items()}
    graph_hash = hash_bytes(b"".join(captured[rel] for rel in rels[1:4]))
    return DeliveryCheck(
        captured["delivery/report.md"],
        hashes["delivery/report.md"],
        plan_hash,
        graph_hash,
        gates,
        tuple(reasons),
        critical,
        hashes,
    )


def revoke_delivery(
    state: RunState, reason: str, *, verification_files: dict[str, str] | None = None
) -> None:
    manifest = state.load_manifest()
    prior = manifest.metadata.get("seal")
    if prior:
        manifest.metadata.setdefault("seal_history", []).append(dict(prior))
    manifest.metadata["seal"] = {
        **(prior or {}),
        "eligible": False,
        "revoked_reason": reason,
    }
    files = dict(verification_files or {})
    for relative, content in files.items():
        manifest.artifact_hashes[relative] = hash_bytes(content.encode("utf-8"))
    path = state._resolve("delivery-manifest.json")
    if path.is_file() and path.stat().st_size:
        from kdrx.schemas.artifact import DeliveryManifest

        try:
            delivery = DeliveryManifest.model_validate_json(path.read_bytes())
        except ValueError:
            delivery = None
        if delivery:
            delivery.final_integrity_pass = False
            delivery.metadata["revoked_reason"] = reason
            files["delivery-manifest.json"] = delivery.model_dump_json(indent=2)
    state.commit_bundle(manifest, files)
    state.append_event({"kind": "delivery_revoked", "reason": reason})


def verify_delivery(run_dir: Path) -> dict:
    """Consumer verification: no network, model or plugin invocation."""
    from kdrx.schemas.artifact import DeliveryManifest

    state = RunState(run_dir.parent, run_dir.name)
    manifest = state.load_manifest()
    delivery = DeliveryManifest.model_validate_json(
        state.read_text("delivery-manifest.json")
    )
    errors = []
    if delivery.run_id != state.run_id:
        errors.append("delivery run identity mismatch")
    if delivery.metadata.get("policy_version") != POLICY_VERSION:
        errors.append("unknown or legacy policy")
    if manifest.metadata.get("seal", {}).get("eligible") is False:
        errors.append("delivery eligibility revoked in committed checkpoint")
    for artifact in delivery.artifacts:
        path = Path(artifact.path)
        if not path.is_absolute():
            path = state._resolve(artifact.path)
        if (
            not path.is_relative_to(state.run_dir)
            or not path.is_file()
            or hash_file(path) != artifact.content_hash
        ):
            errors.append(f"artifact hash mismatch: {artifact.artifact_id}")
    errors.extend(state.verify_hashes(state.load_manifest().artifact_hashes))
    errors.extend(verify_snapshot(state).blocking_reasons)
    if not delivery.is_complete():
        errors.append("delivery revoked, incomplete or inconclusive")
    return {
        "deliverable": not errors,
        "blocking_reasons": errors,
        "policy_version": POLICY_VERSION,
    }


def delivery_status(state: RunState) -> dict:
    """Readiness is independent from task execution status, including on failure."""
    try:
        return verify_delivery(state.run_dir)
    except (ValueError, OSError) as exc:
        return {
            "deliverable": False,
            "blocking_reasons": [f"delivery unavailable: {exc}"],
        }
