"""End-to-end orchestration over a file corpus (routes R3/R4, offline).

This is the integration layer: it threads the research contract, planner, DAG,
scheduler, corpus retrieval, evidence pack, report assembly and the
deterministic gates into one runnable pipeline. It is the concrete proof that
the "cobertura verificável de claims" replaces a raw search count.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kdrx.claims import (
    compute_standing,
    decompose_into_claims,
    derive_edge,
    discover_contradiction_pairs,
    invert_families,
    is_falsifiable,
    search_counterevidence,
)
from kdrx.corpus import independence_families, source_fingerprint, tokenize
from kdrx.dag import compile_dag
from kdrx.planner import plan_gate
from kdrx.reporting import (
    citation_integrity_gate,
    run_report_swarm,
    split_sentences,
)
from kdrx.retrieval import (
    FileCorpus,
    QueryGraph,
    QueryNode,
    SaturationState,
    StoppingCriterion,
)
from kdrx.scheduler import WaveScheduler
from kdrx.schemas.artifact import ArtifactRecord, DeliveryManifest
from kdrx.schemas.claims import Claim, ClaimEvidenceEdge
from kdrx.schemas.corpus import EvidenceSpan, Locator, SourceRecord
from kdrx.schemas.enums import (
    AgentRole,
    ArtifactKind,
    ClaimImportance,
    ClaimType,
    Criticality,
    EdgeRelation,
    EvidenceType,
    Route,
    Standing,
    TaskStage,
    TaskStatus,
)
from kdrx.schemas.plan import (
    AcceptanceCriteria,
    AgentBrief,
    AgentResult,
    Budget,
    PlannerDisposition,
    ResearchPlan,
    RetryPolicy,
    RunManifest,
    TaskSpec,
)
from kdrx.schemas.request import ResearchContract
from kdrx.security import security_gate
from kdrx.state import RunState, hash_file, run_id_from_plan


def _build_query_graph(objective: str, max_children: int = 8) -> QueryGraph:
    """Expande o objective em um query graph determinístico (T-05-02, plan §18.1).

    O nó seed carrega o objective completo; cada cláusula separada por
    ``and``/``,``/``;``/``.`` vira um nó filho com rationale rastreável.
    As queries dirigem o loop de retrieval — nada de "flat list" solta.
    """
    graph = QueryGraph()
    seed = graph.add(
        QueryNode(
            query=objective,
            rationale="seed: objective completo",
            expected_evidence="visão geral do objective",
            node_id="Q-seed",
        )
    )
    clauses = re.split(r"\s+and\s+|[;,.]", objective)
    seen = {objective.strip().lower()}
    for clause in clauses:
        q = clause.strip()
        if not q or not tokenize(q):
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        if len(graph) - 1 >= max_children:
            break
        graph.child_of(
            seed.node_id,
            query=q,
            rationale="cláusula derivada do objective",
            expected_evidence=q,
            node_id=f"Q-{len(graph)}",
        )
    return graph


def _retrieval_tasks(corpus_size: int) -> list[TaskSpec]:
    """A small, well-formed retrieval/verification/synthesis DAG.

    The DAG is intentionally tiny so the demo stays deterministic; the same
    shape generalizes to the full agent taxonomy via the planner council.
    """
    acceptance = lambda s: AcceptanceCriteria(criteria=[s], output_schema="json")  # noqa: E731
    return [
        TaskSpec(
            task_id="T-RETRIEVE",
            kind="retrieval",
            stage=TaskStage.RETRIEVAL,
            wave=0,
            role=AgentRole.PRIMARY_SOURCE_FINDER,
            mission="search the corpus for evidence relevant to the objective",
            outputs=[
                "evidence/spans.jsonl",
                "corpus/sources.jsonl",
                "corpus/dedup.json",
                "retrieval/query_graph.json",
                "corpus/source-id-map.json",
                "claims/claims.jsonl",
                "claims/standings.jsonl",
                "claims/edges.jsonl",
                "claims/contradictions.json",
                "claims/counterevidence.jsonl",
                "claims/unresolved.json",
            ],
            tools=["search"],
            read_only=True,
            acceptance=acceptance("spans extracted"),
            retry_policy=RetryPolicy(max_retries=1),
            budget=Budget(tokens=1, queries=10),
            criticality=Criticality.HIGH,
            owner="retrieval-worker",
            reviewer="source-verifier",
        ),
        TaskSpec(
            task_id="T-VERIFY",
            kind="source_verification",
            stage=TaskStage.VERIFICATION,
            wave=0,
            role=AgentRole.SOURCE_VERIFIER,
            mission="run the source trust gate over every retrieved source",
            # T-02-05: verify DEVE depender de retrieve explicitamente —
            # antes ambos caiam na wave 0 e funcionavam só por ordem de lista;
            # em concorrência real verify poderia iniciar sem sources.
            dependencies=["T-RETRIEVE"],
            outputs=["verification/source_gates.json"],
            tools=["read"],
            read_only=True,
            acceptance=acceptance("all sources graded"),
            retry_policy=RetryPolicy(max_retries=1),
            budget=Budget(tokens=1),
            owner="source-verifier",
        ),
        TaskSpec(
            task_id="T-SYNTHESIZE",
            kind="synthesis",
            stage=TaskStage.SYNTHESIS,
            wave=1,
            role=AgentRole.SYNTHESIS_AGENT,
            mission="assemble the report from the evidence pack",
            dependencies=["T-RETRIEVE", "T-VERIFY"],
            outputs=[
                "delivery/report.md",
                "delivery/outline.json",
                "delivery/section_dag.json",
                "delivery/swarm_log.json",
            ],
            tools=["write"],
            read_only=False,
            acceptance=acceptance("report assembled"),
            retry_policy=RetryPolicy(max_retries=1),
            budget=Budget(tokens=1),
            criticality=Criticality.HIGH,
            owner="synthesis-agent",
            reviewer="independent-reviewer",
        ),
        TaskSpec(
            task_id="T-INTEGRITY",
            kind="integrity",
            stage=TaskStage.REVIEW,
            wave=2,
            role=AgentRole.FINAL_INTEGRITY_AUDITOR,
            mission="run citation and security integrity gates",
            dependencies=["T-SYNTHESIZE"],
            outputs=["verification/integrity.json", "verification/security.json"],
            tools=["read"],
            read_only=True,
            acceptance=acceptance("integrity gates recorded"),
            retry_policy=RetryPolicy(max_retries=0),
            budget=Budget(tokens=1),
            criticality=Criticality.HIGH,
            owner="final-integrity-auditor",
            reviewer="devils-advocate",
        ),
    ]


def build_contract(
    objective: str, route: Route = Route.FILE_AUGMENTED
) -> ResearchContract:
    """Research contract for the offline path (plan §12)."""
    return ResearchContract(
        contract_id="contract-1",
        objective=objective,
        route=route,
        output_format="markdown",
        languages=["en"],
    )


def build_plan(contract: ResearchContract, corpus_size: int = 0) -> ResearchPlan:
    """Default research plan (offline shape; the planner council generalizes it)."""
    return ResearchPlan(
        plan_id=f"plan-{contract.contract_id}",
        contract_id=contract.contract_id,
        route=contract.route.value,
        plan_md="# Plan\n",
        tasks=_retrieval_tasks(corpus_size),
    )


def prepare_run_dir(
    plan: ResearchPlan,
    contract: ResearchContract,
    runs_root: str | Path = ".research",
    run_id: str | None = None,
) -> tuple[RunState, RunManifest]:
    """Scaffold the run dir and persist human- and machine-readable inputs."""
    from kdrx.runtime.executors import EXECUTORS

    issues = EXECUTORS.issues(plan)
    if issues:
        raise ValueError("plan capabilities unavailable: " + "; ".join(issues))
    dag = compile_dag(plan.tasks)
    if not dag.is_valid:
        raise ValueError(
            "invalid plan DAG: " + "; ".join(str(issue) for issue in dag.issues)
        )
    rid = run_id or run_id_from_plan(plan.plan_id)
    state = RunState(runs_root, rid)
    manifest = RunManifest(
        run_id=rid,
        plan_id=plan.plan_id,
        plan_revision=plan.plan_revision,
        contract_id=contract.contract_id,
        route=contract.route.value,
        root_dir="",
    )
    state.scaffold(manifest)
    plan_json = plan.model_dump_json(indent=2)
    # D4: o scaffold também grava provenance — sha256 dos bytes EXATOS
    # persistidos em plan.json (relidos do disco; write_text traduz newlines
    # no Windows, então o hash canônico é o do arquivo, nunca do modelo).
    manifest.metadata["plan"] = {
        "sha256": hashlib.sha256(plan_json.encode("utf-8")).hexdigest(),
        "source": "scaffold-default",
        "review_approved": False,
        "revision": plan.plan_revision,
        "imported_at": None,
    }
    state.commit_bundle(
        manifest,
        {
            "research_contract.yaml": _yaml_contract(contract),
            "research_contract.json": contract.model_dump_json(indent=2),
            "plan.md": plan.plan_md,
            "plan.json": plan_json,
        },
    )
    return state, manifest


class PlanImportError(Exception):
    """Import blocked with a machine-distinguishable failure class (D1).

    ``exit_code`` follows the canonical map: 4 = state conflict (identity
    mismatch, re-import after execution), 1 = structural/semantic gate
    (DAG or plan gate). ``details`` carries structured evidence for stderr.
    """

    def __init__(self, exit_code: int, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.details = details


def import_plan_into_run(
    state: RunState,
    plan: ResearchPlan,
    contract: ResearchContract,
    *,
    source: str,
    review_approved: bool,
    dispositions: list[PlannerDisposition] | None = None,
) -> dict:
    """Deterministic import gate (D1 steps 4-11): validate-then-write.

    Nada é escrito antes de todos os checks passarem. Em ordem: identity
    binding (plan <-> manifest <-> contract), re-import policy (só enquanto
    PENDING e sem tasks executadas), ``compile_dag``, recompute+overwrite de
    waves/ownership, ``plan_gate``, persistência atômica de
    plan.json/plan.md/planner-dispositions.json, provenance no manifest e
    evento ``plan_imported``. Retorna o dict de provenance (D4).
    """
    manifest = state.load_manifest()

    # 4. identity binding — o plan importado não pode rebindar o run
    if plan.plan_id != manifest.plan_id:
        raise PlanImportError(
            4,
            f"identity mismatch: plan.plan_id={plan.plan_id!r} != "
            f"manifest.plan_id={manifest.plan_id!r}",
        )
    if plan.contract_id != contract.contract_id:
        raise PlanImportError(
            4,
            f"identity mismatch: plan.contract_id={plan.contract_id!r} != "
            f"contract.contract_id={contract.contract_id!r}",
        )
    if plan.route != contract.route.value:
        raise PlanImportError(
            4,
            f"identity mismatch: plan.route={plan.route!r} != "
            f"contract.route={contract.route.value!r}",
        )

    # 5. re-import policy: PENDING e sem tasks executadas; caso contrário selado
    if (
        manifest.status != TaskStatus.PENDING
        or manifest.completed_tasks
        or manifest.failed_tasks
    ):
        raise PlanImportError(
            4,
            "run already executed; re-import forbidden",
            {
                "status": manifest.status.value,
                "completed_tasks": manifest.completed_tasks,
                "failed_tasks": manifest.failed_tasks,
            },
        )

    # 6. compile_dag — gate estrutural
    dag = compile_dag(plan.tasks)
    if not dag.is_valid:
        raise PlanImportError(
            1,
            "plan DAG does not compile",
            {"issues": [str(i) for i in dag.issues]},
        )

    # 7. wave policy: recompute + overwrite (o plano persistido é
    # autoconsistente por construção; o campo task.wave é re-derivado)
    wave_of: dict[str, int] = {
        tid: wave for wave, ids in dag.waves.items() for tid in ids
    }
    for task in plan.tasks:
        task.wave = wave_of[task.task_id]
    plan.waves = dag.waves
    plan.ownership = dag.ownership

    # 8. plan_gate (com contract check) — gate semântico
    gate = plan_gate(plan, contract)
    if gate.blocking():
        raise PlanImportError(
            1,
            "plan gate blocked",
            {
                "blocking_reasons": gate.blocking_reasons,
                "checks": [
                    check.model_dump(mode="json")
                    for check in gate.checks
                    if not check.passed
                ],
            },
        )

    # The store rejects a stale revision before exporting any plan bytes.
    previous = manifest.metadata.get("plan") or {}
    revision = int(previous.get("revision", 0)) + 1
    plan.plan_revision = revision
    plan_json = plan.model_dump_json(indent=2)
    files = {"plan.json": plan_json, "plan.md": plan.plan_md}
    if dispositions is not None:
        files["planner-dispositions.json"] = json.dumps(
            [d.model_dump(mode="json") for d in dispositions], indent=2
        )

    # 11. provenance write-back + evento plan_imported
    provenance = {
        # sha256 dos bytes EXATOS persistidos (canon D4; relido do disco para
        # valer por construção contra `kdr status --json.plan_hash_match`).
        "sha256": hashlib.sha256(plan_json.encode("utf-8")).hexdigest(),
        "source": source,
        "review_approved": review_approved,
        "revision": revision,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest.metadata["plan"] = provenance
    manifest.plan_revision = revision
    state.commit_bundle(manifest, files)
    state.append_event(
        {
            "kind": "plan_imported",
            "run_id": manifest.run_id,
            "plan_hash": provenance["sha256"],
            "source": source,
            "review_approved": review_approved,
            "revision": revision,
        }
    )
    return provenance


def execute_plan(
    plan: ResearchPlan,
    contract: ResearchContract,
    corpus: FileCorpus,
    state: RunState,
    precompleted: dict[str, AgentResult] | None = None,
    doi_resolver: Any | None = None,
    model_config: Any | None = None,
) -> tuple[Any, "_FileResearchExecutor"]:
    """Run the wave scheduler over a persisted plan; return (result, executor).

    T-04-02: o manifest transiciona a cada evento do lifecycle (PENDING ->
    RUNNING -> SUCCEEDED/FAILED; completed_tasks/failed_tasks/gate_results)
    e é re-escrito atomicamente — crash entre waves deixa estado consistente.
    T-04-03: ao final,artifact_hashes é selado (manifest.json/events.jsonl
    excluídos — mutáveis por design).
    T-04-06: delivery-manifest.json é emitido com artifact reais + verdicts.
    """
    dag = compile_dag(plan.tasks)
    manifest = state.load_manifest()
    persisted_plan = ResearchPlan.model_validate_json(state.read_text("plan.json"))
    state.store.assert_writable(manifest.model_dump(mode="json"))
    if manifest.status == TaskStatus.CANCELLED:
        raise ValueError("cancelled run cannot be restarted; create a new run")
    if (
        plan != persisted_plan
        or manifest.plan_id != plan.plan_id
        or manifest.contract_id != contract.contract_id
        or manifest.metadata.get("plan", {}).get("sha256")
        != hash_file(state._resolve("plan.json"))
    ):
        raise ValueError("persisted plan identity/hash mismatch")
    if not dag.is_valid:
        raise ValueError("invalid plan DAG")
    from kdrx.runtime.executors import EXECUTORS, capability_key

    issues = EXECUTORS.issues(plan)
    if issues:
        raise ValueError("plan capabilities unavailable: " + "; ".join(issues))
    executor = _FileResearchExecutor(corpus, state, contract.objective, doi_resolver)
    if plan.execution_backend != "offline":
        from kdrx.application.live import LiveFileExecutor

        if model_config is None or model_config.provider != plan.execution_backend:
            raise ValueError("live plan requires matching explicit model configuration")
        config_hash = hashlib.sha256(
            model_config.model_dump_json().encode()
        ).hexdigest()
        prior_config = manifest.metadata.get("model_config_sha256")
        if prior_config and prior_config != config_hash:
            raise ValueError("model configuration is immutable for an existing run")
        manifest.metadata["model_config_sha256"] = config_hash
        executor = LiveFileExecutor(executor, model_config)
    elif model_config is not None:
        raise ValueError(
            "offline plan cannot silently switch to a live backend; create a live plan"
        )
    if precompleted:
        executor.rehydrate()
    manifest.status = TaskStatus.RUNNING
    state.save_manifest(manifest)
    state.store.register_tasks(state.run_id, [t.task_id for t in plan.tasks])
    commit_lock = threading.RLock()
    leases: dict[str, dict] = {}
    workspaces: dict[str, Any] = {}
    keepers: dict[str, Any] = {}

    def inputs_for(task_id: str) -> list[str]:
        task = plan.task_by_id(task_id)
        paths = set(task.inputs) | {"plan.json", "research_contract.json"}
        pending = list(task.dependencies)
        visited = set()
        while pending:
            tid = pending.pop()
            if tid in visited:
                continue
            visited.add(tid)
            dependency = plan.task_by_id(tid)
            paths.update(dependency.outputs)
            pending.extend(dependency.dependencies)
        return sorted(paths)

    def authorized_execute(brief: AgentBrief) -> AgentResult:
        lease = state.store.claim(
            state.run_id,
            brief.task_id,
            "kernel",
            expected_revision=plan.plan_revision,
            seconds=max(
                300, model_config.timeout_seconds + 30 if model_config else 300
            ),
        )
        leases[brief.task_id] = lease
        from kdrx.runtime.leases import LeaseKeeper

        keeper = LeaseKeeper(state.store, lease).start()
        keepers[brief.task_id] = keeper
        brief = brief.model_copy(
            update={
                "run_id": state.run_id,
                "plan_id": plan.plan_id,
                "plan_revision": plan.plan_revision,
                "attempt_id": lease["attempt_id"],
            }
        )
        try:
            from kdrx.runtime.staging import AttemptWorkspace

            workspace = AttemptWorkspace(
                state, lease["attempt_id"], brief.outputs, inputs_for(brief.task_id)
            )
            workspaces[brief.task_id] = workspace
            workspace.cancelled = keeper.cancelled
            local = _FileResearchExecutor(
                corpus.fork(), workspace, contract.objective, doi_resolver
            )
            replay = manifest.metadata.get("retrieval_replay", {}).get(brief.task_id)
            if capability_key(brief) == "retrieval" and replay:
                from kdrx.runtime.blobs import BlobStore

                blobs = BlobStore(state.root / ".blobs")
                sources = [
                    SourceRecord.model_validate_json(line)
                    for line in blobs.get(replay).splitlines()
                    if line.strip()
                ]
                local.corpus.bind_snapshots(sources, blobs)
            if capability_key(brief) != "retrieval":
                local.rehydrate()
            if plan.execution_backend != "offline":
                local = LiveFileExecutor(local, model_config, backend=executor.backend)
            return local(brief)
        except BaseException:
            from kdrx.runtime.store import StateConflict

            keeper.stop()
            try:
                state.store.finish(
                    lease, {"error": "executor failed"}, [], success=False
                )
            except StateConflict:
                pass
            raise

    def emit(event: dict) -> None:
        nonlocal manifest
        with commit_lock:
            state.append_event(event)
            if event.get("kind") == "task_failed" and event.get("task_id") in leases:
                from kdrx.runtime.store import StateConflict

                keepers[event["task_id"]].stop()

                try:
                    state.store.finish(
                        leases[event["task_id"]],
                        {"error": "validation failed"},
                        [],
                        success=False,
                    )
                except StateConflict:
                    pass
            manifest = RunManifest.model_validate(
                state.store.transition(
                    state.run_id, event, expected_revision=plan.plan_revision
                )
            )
            state.flush_exports()

    def validate_result(task: TaskSpec, outcome: AgentResult) -> None:
        from kdrx.application.artifacts import validate_outputs

        from kdrx.runtime.blobs import BlobStore

        with commit_lock:
            lease = leases[task.task_id]
            keepers[task.task_id].check()
            if (
                outcome.run_id != state.run_id
                or outcome.attempt_id != lease["attempt_id"]
                or outcome.plan_id != plan.plan_id
                or outcome.plan_revision != plan.plan_revision
            ):
                raise ValueError("result run/plan/attempt identity mismatch")
            workspace = workspaces[task.task_id]
            workspace.validate_boundary()
            artifacts = validate_outputs(workspace, task, outcome)
            if capability_key(task) == "retrieval":
                from kdrx.application.checkpoints import load_checkpoint

                load_checkpoint(workspace)
            blobs = BlobStore(state.root / ".blobs")
            for artifact in artifacts:
                if (
                    blobs.put(workspace._resolve(artifact["path"]).read_bytes())
                    != artifact["sha256"]
                ):
                    raise ValueError("output changed before commit")
            state.store.finish(
                lease,
                outcome.model_dump(mode="json"),
                artifacts,
                checkpoint={
                    "plan_hash": manifest.metadata["plan"]["sha256"],
                    "input_hashes": workspace.input_hashes,
                },
                staged_events=workspace.staged_events,
            )
            keepers[task.task_id].stop()
            state.flush_exports()

    try:
        result = WaveScheduler(
            authorized_execute, emit=emit, validate_result=validate_result
        ).run(dag, precompleted=precompleted)
    finally:
        for keeper in keepers.values():
            keeper.stop()
    manifest = state.load_manifest()
    if result.completed:
        executor.rehydrate()

    if manifest.metadata["plan"]["revision"] != plan.plan_revision:
        from kdrx.runtime.store import StateConflict

        raise StateConflict(
            "plan revision changed before finalization; resume the current plan"
        )

    # Selo final: status + gates + hashes (T-04-02/03) + delivery manifest (T-04-06)
    if manifest.status != TaskStatus.CANCELLED:
        manifest.status = (
            TaskStatus.SUCCEEDED if not result.failed else TaskStatus.FAILED
        )
    manifest.completed_tasks = list(result.completed)
    manifest.failed_tasks = list(result.failed)
    manifest.gate_results = {
        "integrity": _verdict_of(state, "verification/integrity.json"),
        "security": _verdict_of(state, "verification/security.json"),
    }
    manifest.artifact_hashes = _sealable_hashes(state)
    state.save_manifest(manifest)
    from kdrx.application.delivery import POLICY_VERSION, verify_snapshot

    try:
        check = verify_snapshot(state)
    except (ValueError, OSError):
        check = None
    if check is None or not check.deliverable:
        manifest.gate_results["integrity"] = "fail"
    state.save_manifest(manifest)
    seal_delivery(
        state,
        manifest,
        produced_by="runner:execute_plan",
        gate_timestamps={},
        unresolved_critical=list(check.unresolved_critical)
        if check
        else ["verification-incomplete"],
        verified_report_bytes=check.report_bytes if check else None,
        verification_context={
            "policy_version": POLICY_VERSION,
            "plan_hash": check.plan_hash,
            "graph_revision": check.graph_hash,
        }
        if check
        else {"incomplete": True},
    )
    if check and any(
        hash_file(state._resolve(rel)) != expected
        for rel, expected in check.input_hashes.items()
    ):
        manifest.gate_results["integrity"] = "fail"
        state.save_manifest(manifest)
        delivery = DeliveryManifest.model_validate_json(
            state.read_text("delivery-manifest.json")
        )
        delivery.final_integrity_pass = False
        state.write_text("delivery-manifest.json", delivery.model_dump_json(indent=2))
    manifest.artifact_hashes = _sealable_hashes(state)
    state.save_manifest(manifest)
    result.deliverable = bool(
        check and check.deliverable and manifest.gate_results.get("integrity") == "pass"
    )
    result.blocking_reasons = (
        list(check.blocking_reasons) if check else ["verification-incomplete"]
    )
    if not result.deliverable and not result.blocking_reasons:
        result.blocking_reasons = ["input changed during publication"]
    return result, executor


def _apply_manifest_transition(manifest: RunManifest, event: dict) -> None:
    kind = event.get("kind")
    tid = event.get("task_id")
    if kind == "task_succeeded" and tid and tid not in manifest.completed_tasks:
        manifest.completed_tasks.append(tid)
        manifest.failed_tasks = [t for t in manifest.failed_tasks if t != tid]
    elif kind in ("task_exhausted", "task_blocked") and tid:
        if tid not in manifest.failed_tasks:
            manifest.failed_tasks.append(tid)
        manifest.completed_tasks = [t for t in manifest.completed_tasks if t != tid]


def _verdict_of(state: RunState, rel: str) -> str:
    path = state.run_dir / rel
    if not path.is_file():
        return "missing"
    try:
        return str(
            json.loads(path.read_text(encoding="utf-8")).get("verdict", "unknown")
        )
    except (OSError, json.JSONDecodeError):
        return "unknown"


# Arquivos mutáveis por design (nunca entram no selo de hashes)
_NON_SEALABLE = {"manifest.json", "events.jsonl", "delivery-manifest.json"}


def _sealable_hashes(state: RunState) -> dict[str, str]:
    return {
        rel: h
        for rel, h in state.snapshot_hashes().items()
        if rel.replace("\\", "/") not in _NON_SEALABLE and h
    }


def unresolved_critical_claims(run_dir: str | Path) -> list[str]:
    from kdrx.application.artifacts import load_jsonl

    claims = load_jsonl(Path(run_dir) / "claims/claims.jsonl", Claim)
    return [
        c.claim_id
        for c in claims
        if c.importance == ClaimImportance.CRITICAL
        and c.standing == Standing.UNRESOLVED
    ]


def seal_delivery(
    state: RunState,
    manifest: RunManifest,
    *,
    produced_by: str,
    gate_timestamps: dict[str, str],
    unresolved_critical: list[str],
    verified_report_bytes: bytes | None = None,
    verification_context: dict | None = None,
    verification_files: dict[str, str] | None = None,
) -> DeliveryManifest:
    """Persiste o DeliveryManifest com o hash dos bytes verificados (D1/D2/D7).

    ``verified_report_hash`` vem de uma RELEITURA dos bytes de
    ``delivery/report.md`` em disco (CRLF-safe, lição SW-02) — o manifest
    assevera quais bytes foram verificados no selo (lineage). Idempotente/
    revision-safe: re-emitir sobre os mesmos bytes produz o mesmo hash.
    """
    report_path = state.run_dir / "delivery" / "report.md"
    artifacts: list[ArtifactRecord] = []
    open_ok = False
    verified_report_hash: str | None = None
    if report_path.is_file():
        try:
            data = (
                verified_report_bytes
                if verified_report_bytes is not None
                else report_path.read_bytes()
            )
            open_ok = True
            verified_report_hash = hashlib.sha256(data).hexdigest()
            artifacts.append(
                ArtifactRecord(
                    artifact_id="report",
                    kind=ArtifactKind.REPORT,
                    path=str(report_path),
                    content_hash=verified_report_hash,
                    produced_by=produced_by,
                )
            )
        except OSError:
            open_ok = False
    dm = DeliveryManifest(
        manifest_id=f"dm-{manifest.run_id}",
        run_id=manifest.run_id,
        artifacts=artifacts,
        final_integrity_pass=manifest.gate_results.get("integrity") == "pass",
        secret_scan_clean=manifest.gate_results.get("security") == "pass",
        artifact_open_test_passed=open_ok,
        unresolved_critical_claims=unresolved_critical,
        delivered_at=datetime.now(timezone.utc),
        verified_report_hash=verified_report_hash,
        gate_timestamps=gate_timestamps,
        metadata=verification_context or {},
    )
    files: dict[str, str | bytes] = {
        **(verification_files or {}),
        "delivery-manifest.json": dm.model_dump_json(indent=2),
    }
    for relative, content in (verification_files or {}).items():
        manifest.artifact_hashes[relative] = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()
    if verified_report_bytes is not None and verified_report_hash is not None:
        relative = f"delivery/revisions/{verified_report_hash}.md"
        files[relative] = verified_report_bytes
        manifest.artifact_hashes[relative] = verified_report_hash
    manifest.metadata["seal"] = {
        "eligible": dm.is_complete(),
        "verified_report_hash": verified_report_hash,
        "sealed_at": dm.delivered_at.isoformat(),
        "revision": (verification_context or {}).get("revision", 0),
        "policy_version": (verification_context or {}).get("policy_version"),
    }
    state.commit_bundle(manifest, files)
    return dm


def resume_run(
    state: RunState, corpus: FileCorpus, model_config: Any | None = None
) -> tuple[Any, "_FileResearchExecutor"]:
    """Continua um run existente sem repetir tasks fechadas (T-04-04).

    Reconstrói o DAG do plan.json persistido, marca as tasks já SUCCEEDED
    (via manifest) como pré-completadas — o scheduler lhes pula e suas
    dependências contam como satisfeitas — e executa só a fila restante.
    """
    manifest = state.load_manifest()
    bad = state.verify_hashes(manifest.artifact_hashes)
    state.store.assert_writable(manifest.model_dump(mode="json"))
    if bad:
        raise ValueError(f"resume integrity hash mismatch: {bad}")
    if state.store.reconcile_expired(state.run_id):
        state.flush_exports()
    plan = ResearchPlan.model_validate(json.loads(state.read_text("plan.json")))
    contract = ResearchContract.model_validate(
        json.loads(state.read_text("research_contract.json"))
    )
    precompleted: dict[str, AgentResult] = {}
    completed = set(manifest.completed_tasks)
    for task in plan.tasks:
        if task.task_id in completed:
            path = state._resolve(f"tasks/{task.task_id}/result.json")
            if not path.is_file() or task.task_id not in manifest.metadata.get(
                "task_commits", {}
            ):
                raise ValueError(
                    f"missing verified task receipt for {task.task_id}; legacy run requires explicit migration"
                )
            precompleted[task.task_id] = AgentResult.model_validate_json(
                path.read_bytes()
            )
            WaveScheduler._validate_outcome(task, precompleted[task.task_id])
    from kdrx.application.checkpoints import validate_task_receipts

    validate_task_receipts(state, plan, manifest, precompleted)
    if len(precompleted) == len(plan.tasks) and manifest.status == TaskStatus.SUCCEEDED:
        from kdrx.application.delivery import verify_delivery
        from kdrx.scheduler import ScheduleResult

        # A fully published run is a read-only replay. If publication was
        # interrupted before its transaction, finalize below without inference.
        path = state._resolve("delivery-manifest.json")
        if path.is_file() and path.stat().st_size:
            verification = verify_delivery(state.run_dir)
            executor = _FileResearchExecutor(corpus, state, contract.objective)
            executor.rehydrate()
            return ScheduleResult(
                completed=[t.task_id for t in plan.tasks],
                deliverable=verification["deliverable"],
                blocking_reasons=verification["blocking_reasons"],
            ), executor
    return execute_plan(
        plan,
        contract,
        corpus,
        state,
        precompleted=precompleted,
        model_config=model_config,
    )


class _FileResearchExecutor:
    """Deterministic executor: real file-corpus retrieval + gate recording."""

    def __init__(
        self,
        corpus: FileCorpus,
        state: RunState,
        objective: str,
        doi_resolver: Any | None = None,
    ) -> None:
        self.corpus = corpus
        self.state = state
        self.objective = objective
        self.doi_resolver = doi_resolver
        self.sources: list[SourceRecord] = []
        self.spans: list[EvidenceSpan] = []
        self.claims: list[Claim] = []
        self.report_text = ""

    def rehydrate(self) -> None:
        from kdrx.application.checkpoints import load_checkpoint

        checkpoint = load_checkpoint(self.state)
        self.sources = checkpoint.sources
        self.spans = checkpoint.spans
        self.claims = checkpoint.claims
        self.report_text = checkpoint.report
        from kdrx.runtime.blobs import BlobStore

        self.corpus.bind_snapshots(self.sources, BlobStore(self.state.root / ".blobs"))

    def __call__(self, brief: AgentBrief) -> AgentResult:
        from kdrx.runtime.executors import EXECUTORS

        outcome = EXECUTORS.execute(self, brief)
        return outcome.model_copy(
            update={
                "run_id": brief.run_id,
                "plan_id": brief.plan_id,
                "plan_revision": brief.plan_revision,
                "attempt_id": brief.attempt_id,
            }
        )

    def _retrieve(self, brief: AgentBrief) -> AgentResult:
        docs = self.corpus.scan()
        original_sources = {doc.doc_id: doc.source for doc in docs}
        # T-05-06: dedup por fingerprint de conteúdo — cópias idênticas do
        # mesmo texto colapsam para a fonte CANÔNICA (1a ocorrência). Spans das
        # cópias citam a fonte canônica, então o standing mede independência
        # real e o gate não sequer vê fontes-fantasma. O dedup é artifact do
        # run (corpus/dedup.json), nunca apagamento silencioso.
        canon_by_fp: dict[str, SourceRecord] = {}
        duplicates: dict[str, str] = {}
        for d in docs:
            s = d.source
            if s is None:
                continue
            fp = source_fingerprint(s)
            canon = canon_by_fp.get(fp)
            if canon is None:
                canon_by_fp[fp] = s
            else:
                duplicates[s.source_id] = canon.source_id
                d.source = canon
        self.sources = list(canon_by_fp.values())
        from kdrx.runtime.blobs import BlobStore

        blobs = BlobStore(self.state.root / ".blobs")
        for doc in docs:
            if doc.source is not None:
                blobs.put(doc.text.encode("utf-8"))
                raw = self.corpus.raw_bytes(doc)
                if hashlib.sha256(raw).hexdigest() != original_sources[
                    doc.doc_id
                ].metadata.get("raw_bytes_hash"):
                    raise ValueError("source changed before snapshot")
                blobs.put(raw)
        self.state.write_text(
            "corpus/source-id-map.json",
            json.dumps(
                {
                    s.metadata.get("legacy_source_id"): s.source_id
                    for s in original_sources.values()
                    if s
                }
            ),
        )
        families = independence_families(self.sources)
        self.state.write_text(
            "corpus/dedup.json",
            json.dumps(
                {
                    "duplicates": duplicates,
                    "canonical_count": len(self.sources),
                    "scanned_documents": len(docs),
                    "families": {k: sorted(v) for k, v in families.items()},
                },
                indent=2,
            )
            + "\n",
        )

        # T-05-02/T-05-07: o QueryGraph dirige o loop de retrieval (seed +
        # cláusulas do objective); o StoppingCriterion decide a parada por
        # saturação de evidência — margens medidas por ganho REAL de
        # fontes/termos (proxy determinístico de claims, plan §18.5).
        graph = _build_query_graph(self.objective)
        stopping = StoppingCriterion()
        objective_terms = {t for t in tokenize(self.objective) if len(t) >= 4}

        merged: list[dict] = []
        seen_spans: set[tuple[str, object]] = set()
        known_sources: set[str] = set()
        covered_terms: set[str] = set()
        queries_issued = 0
        decision: dict = {"stop": False, "reason": "not_evaluated", "unmet": []}

        for node in graph:
            prior_sources = len(known_sources)
            hits = self.corpus.retrieve_evidence_spans(node.query, top_k=5, window=40)
            queries_issued += 1
            node_results: list[str] = []
            new_sources = 0
            new_terms = 0
            for h in hits:
                src = h["source_id"]
                node_results.append(src)
                key = (src, h["locator"]["char_start"])
                if key in seen_spans:
                    continue
                seen_spans.add(key)
                merged.append(h)
                if src not in known_sources:
                    new_sources += 1
                terms_here = set(tokenize(h["verbatim_span"])) & objective_terms
                new_terms += len(terms_here - covered_terms)
                covered_terms |= terms_here
            node.results = sorted(set(node_results))
            node.marginal_gain = float(new_sources)

            gain_src = (
                (1.0 if new_sources else 0.0)
                if prior_sources == 0
                else new_sources / prior_sources
            )
            gain_ev = new_terms / max(1, len(objective_terms))
            known_sources |= set(node_results)
            coverage = len(covered_terms) / max(1, len(objective_terms))
            decision = stopping.evaluate(
                SaturationState(
                    critical_claim_coverage=0.0,
                    marginal_source_gain=gain_src,
                    marginal_evidence_gain=gain_ev,
                    unresolved_blockers=len(graph.nodes),
                    diversity_sources=len(known_sources),
                    queries_issued=queries_issued,
                )
            )
            if decision["stop"]:
                break

        self.spans = [
            EvidenceSpan(
                evidence_id=f"EV-{i}",
                source_id=h["source_id"],
                locator=Locator(**h["locator"]),
                verbatim_span=h["verbatim_span"],
                normalized_proposition=self.objective,
                evidence_type=EvidenceType.VERBATIM,
                extraction_method="bm25+rrf",
                extractor="file-corpus",
                verified=True,
            )
            for i, h in enumerate(merged)
        ]
        self.state.write_text(
            "corpus/sources.jsonl",
            "\n".join(s.model_dump_json() for s in self.sources) + "\n",
        )
        self.state.write_text(
            "evidence/spans.jsonl",
            "\n".join(s.model_dump_json() for s in self.spans) + "\n",
        )
        # T-05-02: provenance do grafo e da decisão de parada é artifact do run
        self.state.write_text(
            "retrieval/query_graph.json",
            json.dumps(
                {
                    "objective": self.objective,
                    "queries_issued": queries_issued,
                    "lexical_query_coverage": coverage if queries_issued else 0.0,
                    "research_coverage": None,
                    "decision": decision,
                    "nodes": [
                        {
                            "node_id": n.node_id,
                            "query": n.query,
                            "rationale": n.rationale,
                            "parent": n.parent,
                            "results": n.results,
                            "marginal_gain": n.marginal_gain,
                        }
                        for n in graph
                    ],
                },
                indent=2,
            )
            + "\n",
        )
        self._extract_claims()
        self._compute_standings()
        return AgentResult(
            result_id="r-retrieve",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
            evidence_refs=[s.evidence_id for s in self.spans],
            limitations=[
                f"file corpus; {len(docs)} docs; graph {len(graph)} nodes / "
                f"{queries_issued} queries ({decision['reason']})"
            ],
            declared_tests=[],
            executed_tests=[],
        )

    def _extract_claims(self) -> None:
        """Derive atomic claims from sentences that overlap the objective.

        T-07-01: decomposição ESTRUTURADA — sentences candidatas (overlap com o
        objetivo ou predicado falsificável) passam pelo decomposer: compostos
        viram claims atômicos com scope extraído. Cada claim é ligado ao
        evidence span do seu documento para o loop claim -> evidence -> standing.
        """
        objective_tokens = set(tokenize(self.objective))
        seen_claims: set[tuple[str, str]] = set()
        for doc in self.corpus._docs:
            source_id = doc.source.source_id if doc.source else doc.doc_id
            for sent in split_sentences(doc.text):
                sent_tokens = set(tokenize(sent))
                if len(sent_tokens & objective_tokens) < 2 and not is_falsifiable(sent):
                    continue
                for claim in decompose_into_claims(f"CL-{len(self.claims) + 1}", sent):
                    # T-05-06: cópias colapsadas para a fonte canônica não
                    # geram claims duplicados — (statement, source) é único.
                    key = (claim.statement.strip().lower(), source_id)
                    if key in seen_claims:
                        continue
                    seen_claims.add(key)
                    start = doc.text.find(sent)
                    ev = next(
                        (
                            sp
                            for sp in self.spans
                            if sp.source_id == source_id
                            and sp.locator.char_start is not None
                            and sp.locator.char_end is not None
                            and sp.locator.char_start <= start
                            and sp.locator.char_end >= start + len(sent)
                            and sent in sp.verbatim_span
                        ),
                        None,
                    )
                    if ev is None and start >= 0:
                        ev = EvidenceSpan(
                            evidence_id=f"EV-exact-{len(self.spans)}",
                            source_id=source_id,
                            locator=Locator(
                                char_start=start, char_end=start + len(sent)
                            ),
                            verbatim_span=sent,
                            verified=True,
                            content_hash=hashlib.sha256(doc.text.encode()).hexdigest(),
                            extractor="file-corpus",
                            extraction_method="exact-sentence",
                        )
                        self.spans.append(ev)
                    claim.metadata["origin_statement"] = sent
                    claim.claim_type = ClaimType.DESCRIPTIVE
                    claim.importance = ClaimImportance.MAJOR
                    claim.support_edges = [ev.evidence_id] if ev else []
                    self.claims.append(claim)
        self.state.write_text(
            "claims/claims.jsonl",
            "\n".join(c.model_dump_json() for c in self.claims) + "\n",
        )
        self.state.write_text(
            "evidence/spans.jsonl",
            "\n".join(s.model_dump_json() for s in self.spans) + "\n",
        )

    def _compute_standings(self) -> dict[str, dict]:
        """Compute standing for every claim and persist standings/edges.

        T-07-04: pares contraditórios são DESCOBERTOS (numeric/polarity), não
        fornecidos. T-07-05: o falsification swarm executa busca ativa de
        counterevidence por claim. T-07-06: edges derivados (entailment,
        quality, independence, confidence) — zero scores constantes.
        T-07-07: claims UNRESOLVED vão para o registry claims/unresolved.json.
        """
        from kdrx.verification import cluster_contradictions

        families = independence_families(self.sources)
        source_family = invert_families(families)
        family_size = {
            sid: len(families.get(fam, [sid])) for sid, fam in source_family.items()
        }
        evidence_source = {sp.evidence_id: sp.source_id for sp in self.spans}
        span_by_id = {sp.evidence_id: sp for sp in self.spans}
        source_by_id = {s.source_id: s for s in self.sources}
        claim_by_id = {c.claim_id: c for c in self.claims}

        # T-07-04: descoberta automática de contradições (sem pares fornecidos)
        pairs = discover_contradiction_pairs(self.claims)
        contradiction_clusters = cluster_contradictions(self.claims, pairs)
        contra_claims: dict[str, list[str]] = {}
        for a_id, b_id in pairs:
            contra_claims.setdefault(a_id, []).append(b_id)
            contra_claims.setdefault(b_id, []).append(a_id)
        self.state.write_text(
            "claims/contradictions.json",
            json.dumps(
                [c.model_dump(mode="json") for c in contradiction_clusters], indent=2
            )
            + "\n",
        )

        # T-07-05: busca ativa de counterevidence (falsification swarm executado)
        counter_hits = []
        for c in self.claims:
            own_span = next(
                (span_by_id[e] for e in c.support_edges if e in span_by_id), None
            )
            own_source = (
                source_by_id.get(own_span.source_id) if own_span is not None else None
            )
            own_doc = own_source.metadata.get("original_path") if own_source else None
            counter_hits.extend(
                search_counterevidence(c, self.corpus, own_source_id=own_doc)
            )
        self.state.write_text(
            "claims/counterevidence.jsonl",
            "".join(json.dumps(h.__dict__) + "\n" for h in counter_hits),
        )
        counter_edges: dict[str, list[ClaimEvidenceEdge]] = {}
        assessed_hits = []
        docs_by_id = {doc.doc_id: doc for doc in self.corpus._docs}
        for hit in counter_hits:
            doc = docs_by_id.get(hit.doc_id)
            claim = claim_by_id[hit.claim_id]
            if doc is None or doc.source is None:
                assessed_hits.append(
                    {**hit.__dict__, "assessment": "source_unavailable"}
                )
                continue
            source = doc.source
            if source.source_id not in source_by_id:
                self.sources.append(source)
                source_by_id[source.source_id] = source
            relations = []
            for sentence in split_sentences(doc.text):
                start = doc.text.find(sentence)
                span = EvidenceSpan(
                    evidence_id="EV-counter-"
                    + hashlib.sha256(
                        (claim.claim_id + source.source_id + sentence).encode()
                    ).hexdigest()[:24],
                    source_id=source.source_id,
                    verbatim_span=sentence,
                    locator=Locator(char_start=start, char_end=start + len(sentence)),
                    verified=True,
                    content_hash=hashlib.sha256(doc.text.encode()).hexdigest(),
                    extraction_method="counterevidence-exact-sentence",
                )
                edge = derive_edge(
                    claim,
                    span,
                    source=source,
                    family_size=family_size.get(source.source_id, 1),
                )
                if edge.relation in {EdgeRelation.CONTRADICTS, EdgeRelation.QUALIFIES}:
                    if span.evidence_id not in span_by_id:
                        self.spans.append(span)
                        span_by_id[span.evidence_id] = span
                        evidence_source[span.evidence_id] = source.source_id
                    counter_edges.setdefault(claim.claim_id, []).append(edge)
                    relations.append(edge.relation.value)
            assessed_hits.append(
                {
                    **hit.__dict__,
                    "relations": relations,
                    "assessment": "assessed"
                    if relations
                    else "irrelevant_or_insufficient",
                }
            )
        self.state.write_text(
            "claims/counterevidence.jsonl",
            "".join(json.dumps(item) + "\n" for item in assessed_hits),
        )
        self.state.write_text(
            "evidence/spans.jsonl",
            "".join(span.model_dump_json() + "\n" for span in self.spans),
        )
        self.state.write_text(
            "corpus/sources.jsonl",
            "".join(source.model_dump_json() + "\n" for source in self.sources),
        )

        standings: dict[str, dict] = {}
        edges_out: list[dict] = []
        for c in self.claims:
            # T-07-06: cada edge é DERIVADO — entailment verificado, quality
            # dos atributos da fonte, independence da família, confidence da
            # extração (ver derive_edge; a base vai em limitations).
            sup = [
                derive_edge(
                    c,
                    span_by_id[e],
                    source=source_by_id.get(span_by_id[e].source_id),
                    family_size=family_size.get(span_by_id[e].source_id, 1),
                )
                for e in c.support_edges
                if e in span_by_id
            ]
            contra: list[ClaimEvidenceEdge] = list(counter_edges.get(c.claim_id, []))
            for other_id in contra_claims.get(c.claim_id, []):
                other = claim_by_id[other_id]
                for e in other.support_edges:
                    sp = span_by_id.get(e)
                    if sp is None:
                        continue
                    edge = derive_edge(
                        other,
                        sp,
                        source=source_by_id.get(sp.source_id),
                        family_size=family_size.get(sp.source_id, 1),
                    )
                    contra.append(
                        edge.model_copy(
                            update={
                                "edge_id": f"E-{c.claim_id}-contra-{sp.evidence_id}",
                                "claim_id": c.claim_id,
                                "relation": EdgeRelation.CONTRADICTS,
                            }
                        )
                    )
            res = compute_standing(
                c,
                sup,
                contra,
                evidence_source=evidence_source,
                source_family=source_family,
            )
            c.standing = res.standing
            c.contradiction_edges = [
                edge.evidence_id
                for edge in contra
                if edge.relation == EdgeRelation.CONTRADICTS
            ]
            c.confidence = res.confidence
            c.calibration_basis = res.calibration_basis
            standings[c.claim_id] = res.as_dict()
            edges_out.extend(e.model_dump() for e in sup)
            edges_out.extend(e.model_dump() for e in contra)
        self.state.write_text(
            "claims/standings.jsonl",
            "\n".join(json.dumps(v) for v in standings.values()) + "\n",
        )
        self.state.write_text(
            "claims/edges.jsonl", "\n".join(json.dumps(e) for e in edges_out) + "\n"
        )
        # T-01-07: repersist claims COM standing final — o arquivo escrito em
        # _extract_claims tinha standing=UNRESOLVED default; sem isto o
        # `kdr verify` (que relê do disco) diverge do gate in-memory.
        self.state.write_text(
            "claims/claims.jsonl",
            "\n".join(c.model_dump_json() for c in self.claims) + "\n",
        )
        # T-07-07: UNRESOLVED registry — todo claim não resolvido é disclosado
        # com razão auditável (sem span vs. score abaixo dos thresholds).
        unresolved = [c for c in self.claims if c.standing == Standing.UNRESOLVED]
        registry = [
            {
                "claim_id": c.claim_id,
                "statement": c.statement,
                "reason": (
                    "no_evidence_span"
                    if not c.support_edges
                    else "score_below_threshold"
                ),
                "calibration_basis": c.calibration_basis,
            }
            for c in unresolved
        ]
        self.state.write_text(
            "claims/unresolved.json", json.dumps(registry, indent=2) + "\n"
        )
        return standings

    def _verify(self, brief: AgentBrief) -> AgentResult:
        from kdrx.verification import record_doi, source_trust_gate

        # B-06/T-04-07: corpus vazio NÃO pode retornar sucesso — a existência
        # de fonte verificável é pré-condição do pipeline; falha bloqueia a wave.
        if not self.sources:
            raise RuntimeError(
                "source trust gate: corpus sem fontes verificáveis (empty corpus blocks)"
            )
        # T-06-01/07: quando um resolver vivo está configurado, fontes com DOI
        # ganham checks de resolução BLOCKING (fabricado/misrouted => FAIL).
        gates = []
        for s in self.sources:
            resolution = None
            if self.doi_resolver is not None:
                doi = record_doi(s)
                if doi:
                    resolution = self.doi_resolver.resolve(doi)
            gates.append(source_trust_gate(s, resolution=resolution).model_dump())
        blocking_failures = [
            g["gate_id"] for g in gates if g["verdict"] in ("fail", "blocked")
        ]
        self.state.write_text(
            "verification/source_gates.json", json.dumps(gates, indent=2)
        )
        if blocking_failures:
            raise RuntimeError(f"source trust gate FAILED: {blocking_failures}")
        return AgentResult(
            result_id="r-verify",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
            evidence_refs=[s.source_id for s in self.sources],
            limitations=[f"{len(gates)} sources graded"],
        )

    def _analyze_claims(self, brief: AgentBrief) -> AgentResult:
        self.state.write_text(
            brief.outputs[0],
            json.dumps(
                {
                    "method": "persisted-deterministic-standing",
                    "claims": [
                        {
                            "claim_id": c.claim_id,
                            "standing": c.standing.value,
                            "confidence": c.confidence,
                            "calibration_basis": c.calibration_basis,
                            "support": c.support_edges,
                            "counterevidence": c.contradiction_edges,
                        }
                        for c in self.claims
                    ],
                    "limitations": [
                        "heuristic standing; no independently calibrated entailment model"
                    ],
                },
                indent=2,
            ),
        )
        return AgentResult(
            result_id="r-claim-analysis",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
            evidence_refs=[s.evidence_id for s in self.spans],
        )

    def _export_evidence(self, brief: AgentBrief) -> AgentResult:
        if len(brief.outputs) != 1 or not brief.outputs[0].endswith(".json"):
            raise ValueError(
                "artifact_export currently supports one JSON evidence pack"
            )
        self.state.write_text(
            brief.outputs[0],
            json.dumps(
                {
                    "schema_version": "0.3",
                    "sources": [s.model_dump(mode="json") for s in self.sources],
                    "spans": [s.model_dump(mode="json") for s in self.spans],
                    "claims": [c.model_dump(mode="json") for c in self.claims],
                },
                indent=2,
            ),
        )
        return AgentResult(
            result_id="r-evidence-export",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
            evidence_refs=[s.evidence_id for s in self.spans],
        )

    def _synthesize(self, brief: AgentBrief) -> AgentResult:
        # T-08-01..06: o report nasce do SWARM — council de outline, section
        # DAG (uma task por seção), packs mínimos, writer/reviewer/fixer/
        # transition editor separados, summary/conclusion tardios e citation
        # manager (references = só citadas).
        swarm = run_report_swarm(self.objective, self.claims, self.sources, self.spans)
        self.report_text = swarm.report_text
        self.state.write_text(brief.outputs[0], self.report_text)
        self.state.write_text(
            "delivery/outline.json",
            json.dumps(
                {
                    "council_rounds": [
                        {
                            "round_no": r.round_no,
                            "proposals": r.proposals,
                            "elected": r.elected,
                        }
                        for r in swarm.council_rounds
                    ],
                    "sections": [
                        {
                            "section_id": s.section_id,
                            "title": s.title,
                            "theme": s.theme,
                            "late": s.late,
                            "claims": s.claim_ids,
                        }
                        for s in swarm.outline
                    ],
                },
                indent=2,
            )
            + "\n",
        )
        self.state.write_text(
            "delivery/section_dag.json",
            json.dumps({"waves": swarm.section_waves}, indent=2) + "\n",
        )
        self.state.write_text(
            "delivery/swarm_log.json",
            json.dumps(
                {
                    "generation_order": swarm.generation_order,
                    "reviews": swarm.review_log,
                },
                indent=2,
            )
            + "\n",
        )
        return AgentResult(
            result_id="r-synthesize",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
            evidence_refs=[sp.evidence_id for sp in self.spans],
            limitations=["synthesis is deterministic; no LLM writer attached"],
            declared_tests=[],
            executed_tests=[],
            payload={
                "sections": len(swarm.outline),
                "claims": len(self.claims),
                "references": len(swarm.references),
            },
        )

    def _integrity(self, brief: AgentBrief) -> AgentResult:
        citation = citation_integrity_gate(
            self.report_text, sources=self.sources, claims=self.claims, spans=self.spans
        )
        security = security_gate(self.state.run_dir)
        self.state.write_text(
            "verification/integrity.json", citation.model_dump_json(indent=2)
        )
        self.state.write_text(
            "verification/security.json", security.model_dump_json(indent=2)
        )
        # T-08-07: integridade final é HARD — um gate de citação/segurança
        # falho BLOQUEIA a entrega (antes era só registro com WARN).
        if citation.blocking():
            raise RuntimeError(
                f"final integrity gate FAILED: {citation.blocking_reasons}"
            )
        if security.blocking():
            raise RuntimeError(f"security gate FAILED: {security.blocking_reasons}")
        return AgentResult(
            result_id="r-integrity",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
            evidence_refs=[],
            limitations=[],
            payload={
                "citation_verdict": citation.verdict.value,
                "security_verdict": security.verdict.value,
            },
        )


def run_file_research(
    corpus_dir: str | Path,
    objective: str,
    runs_root: str | Path = ".research",
    *,
    run_id: str | None = None,
    live: bool = False,
) -> dict[str, Any]:
    """Run the full offline pipeline and return a JSON-serializable summary.

    ``live=True`` ativa a verificação viva de fontes (T-06-01): DOIs são
    resolvidos via doi.org durante o source trust gate — depende de rede e é
    desligado por padrão (pipeline offline determinístico).
    """
    corpus = FileCorpus(corpus_dir)
    docs = corpus.scan()

    contract = build_contract(objective)
    plan = build_plan(contract, len(docs))

    gate = plan_gate(plan, contract)
    if gate.blocking():
        return {
            "run_id": None,
            "plan_gate": gate.verdict.value,
            "blocking_reasons": gate.blocking_reasons,
            "exit_code": 1,
        }

    doi_resolver = None
    if live:
        from kdrx.verification import DOIResolver

        doi_resolver = DOIResolver()

    state, _manifest = prepare_run_dir(plan, contract, runs_root, run_id)
    result, executor = execute_plan(
        plan, contract, corpus, state, doi_resolver=doi_resolver
    )

    report_path = state.run_dir / "delivery" / "report.md"
    return {
        "run_id": state.run_dir.name,
        "route": contract.route.value,
        "objective": objective,
        "documents": len(docs),
        "sources": len(executor.sources),
        "spans": len(executor.spans),
        "report": str(report_path),
        "plan_gate": gate.verdict.value,
        "completed_tasks": result.completed,
        "failed_tasks": result.failed,
        "events": len(result.events),
        "deliverable": result.deliverable,
        "blocking_reasons": result.blocking_reasons,
        "exit_code": 0 if result.deliverable else 1,
    }


def _yaml_contract(contract: ResearchContract) -> str:
    d = contract.model_dump(mode="json")
    lines = []
    for k, v in d.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(map(str, v))}]")
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n"
