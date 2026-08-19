"""End-to-end orchestration over a file corpus (routes R3/R4, offline).

This is the integration layer: it threads the research contract, planner, DAG,
scheduler, corpus retrieval, evidence pack, report assembly and the
deterministic gates into one runnable pipeline. It is the concrete proof that
the "cobertura verificável de claims" replaces a raw search count.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kdrx.claims import compute_standing, invert_families
from kdrx.corpus import independence_families, tokenize
from kdrx.dag import compile_dag
from kdrx.planner import plan_gate
from kdrx.reporting import (
    ReportAssembler,
    build_evidence_pack,
    citation_integrity_gate,
    split_sentences,
)
from kdrx.retrieval import FileCorpus
from kdrx.scheduler import WaveScheduler
from kdrx.schemas.claims import Claim, ClaimEvidenceEdge
from kdrx.schemas.corpus import EvidenceSpan, Locator, SourceRecord
from kdrx.schemas.enums import (
    AgentRole,
    ClaimImportance,
    ClaimType,
    Criticality,
    EdgeDirectness,
    EdgeRelation,
    EvidenceType,
    Route,
    TaskStage,
)
from kdrx.schemas.plan import (
    AcceptanceCriteria,
    AgentBrief,
    AgentResult,
    Budget,
    ResearchPlan,
    RetryPolicy,
    RunManifest,
    TaskSpec,
)
from kdrx.schemas.request import ResearchContract
from kdrx.security import security_gate
from kdrx.state import RunState, run_id_from_plan


def _retrieval_tasks(corpus_size: int) -> list[TaskSpec]:
    """A small, well-formed retrieval/verification/synthesis DAG.

    The DAG is intentionally tiny so the demo stays deterministic; the same
    shape generalizes to the full agent taxonomy via the planner council.
    """
    acceptance = lambda s: AcceptanceCriteria(criteria=[s], output_schema="json")  # noqa: E731
    return [
        TaskSpec(
            task_id="T-RETRIEVE",
            stage=TaskStage.RETRIEVAL,
            wave=0,
            role=AgentRole.PRIMARY_SOURCE_FINDER,
            mission="search the corpus for evidence relevant to the objective",
            outputs=["evidence/spans.jsonl", "corpus/sources.jsonl"],
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
            stage=TaskStage.SYNTHESIS,
            wave=1,
            role=AgentRole.SYNTHESIS_AGENT,
            mission="assemble the report from the evidence pack",
            dependencies=["T-RETRIEVE", "T-VERIFY"],
            outputs=["delivery/report.md"],
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
    rid = run_id or run_id_from_plan(plan.plan_id)
    state = RunState(runs_root, rid)
    manifest = RunManifest(
        run_id=rid,
        plan_id=plan.plan_id,
        contract_id=contract.contract_id,
        route=contract.route.value,
        root_dir="",
    )
    state.scaffold(manifest)
    state.write_text("research_contract.yaml", _yaml_contract(contract))
    state.write_text("research_contract.json", contract.model_dump_json(indent=2))
    state.write_text("plan.md", plan.plan_md)
    state.write_text("plan.json", plan.model_dump_json(indent=2))
    return state, manifest


def execute_plan(
    plan: ResearchPlan,
    contract: ResearchContract,
    corpus: FileCorpus,
    state: RunState,
) -> tuple[Any, "_FileResearchExecutor"]:
    """Run the wave scheduler over a persisted plan; return (result, executor)."""
    dag = compile_dag(plan.tasks)
    executor = _FileResearchExecutor(corpus, state, contract.objective)
    result = WaveScheduler(executor, emit=state.append_event).run(dag)
    return result, executor


class _FileResearchExecutor:
    """Deterministic executor: real file-corpus retrieval + gate recording."""

    def __init__(self, corpus: FileCorpus, state: RunState, objective: str) -> None:
        self.corpus = corpus
        self.state = state
        self.objective = objective
        self.sources: list[SourceRecord] = []
        self.spans: list[EvidenceSpan] = []
        self.claims: list[Claim] = []
        self.report_text = ""

    def __call__(self, brief: AgentBrief) -> AgentResult:
        task_id = brief.task_id
        if task_id == "T-RETRIEVE":
            return self._retrieve(brief)
        if task_id == "T-VERIFY":
            return self._verify(brief)
        if task_id == "T-SYNTHESIZE":
            return self._synthesize(brief)
        if task_id == "T-INTEGRITY":
            return self._integrity(brief)
        raise RuntimeError(f"unknown task {task_id}")

    def _retrieve(self, brief: AgentBrief) -> AgentResult:
        docs = self.corpus.scan()
        hits = self.corpus.retrieve_evidence_spans(self.objective, top_k=5, window=40)
        self.sources = [d.source for d in docs if d.source is not None]
        self.spans = [
            EvidenceSpan(
                evidence_id=f"EV-{i}",
                source_id=h["source_id"],
                locator=Locator(file=h["locator"]["file"]),
                verbatim_span=h["verbatim_span"],
                normalized_proposition=self.objective,
                evidence_type=EvidenceType.VERBATIM,
                extraction_method="bm25",
                extractor="file-corpus",
                verified=True,
            )
            for i, h in enumerate(hits)
        ]
        self.state.write_text(
            "corpus/sources.jsonl",
            "\n".join(s.model_dump_json() for s in self.sources) + "\n",
        )
        self.state.write_text(
            "evidence/spans.jsonl",
            "\n".join(s.model_dump_json() for s in self.spans) + "\n",
        )
        self._extract_claims()
        return AgentResult(
            result_id="r-retrieve",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
            evidence_refs=[s.evidence_id for s in self.spans],
            limitations=[f"file corpus only; {len(docs)} documents indexed"],
            declared_tests=[],
            executed_tests=[],
        )

    def _extract_claims(self) -> None:
        """Derive atomic claims from sentences that overlap the objective.

        Each claim is linked to the evidence span of its source document so the
        claim -> evidence -> standing loop is exercised deterministically.
        """
        objective_tokens = set(tokenize(self.objective))
        span_by_source = {sp.source_id: sp for sp in self.spans}
        for doc in self.corpus._docs:
            source_id = doc.source.source_id if doc.source else doc.doc_id
            for sent in split_sentences(doc.text):
                sent_tokens = set(tokenize(sent))
                has_number = any(ch.isdigit() for ch in sent)
                if len(sent_tokens & objective_tokens) >= 2 or has_number:
                    ev = span_by_source.get(source_id)
                    cid = f"CL-{len(self.claims) + 1}"
                    self.claims.append(
                        Claim(
                            claim_id=cid,
                            statement=sent,
                            claim_type=ClaimType.DESCRIPTIVE,
                            importance=ClaimImportance.MAJOR,
                            support_edges=[ev.evidence_id] if ev else [],
                        )
                    )
        self.state.write_text(
            "claims/claims.jsonl",
            "\n".join(c.model_dump_json() for c in self.claims) + "\n",
        )

    def _compute_standings(self) -> dict[str, dict]:
        """Compute standing for every claim and persist standings/edges."""
        families = independence_families(self.sources)
        source_family = invert_families(families)
        evidence_source = {sp.evidence_id: sp.source_id for sp in self.spans}
        standings: dict[str, dict] = {}
        edges_out: list[dict] = []
        for c in self.claims:
            sup = [
                ClaimEvidenceEdge(
                    edge_id=f"E-{c.claim_id}",
                    claim_id=c.claim_id,
                    evidence_id=e,
                    relation=EdgeRelation.SUPPORTS,
                    directness=EdgeDirectness.DIRECT,
                    source_quality=0.8,
                    independence=1.0,
                    scope_match=True,
                    confidence=0.8,
                )
                for e in c.support_edges
            ]
            res = compute_standing(
                c, sup, [], evidence_source=evidence_source, source_family=source_family
            )
            c.standing = res.standing
            c.confidence = res.confidence
            c.calibration_basis = res.calibration_basis
            standings[c.claim_id] = res.as_dict()
            edges_out.extend(e.model_dump() for e in sup)
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
        return standings

    def _verify(self, brief: AgentBrief) -> AgentResult:
        from kdrx.verification import source_trust_gate

        gates = [source_trust_gate(s).model_dump() for s in self.sources]
        self.state.write_text(
            "verification/source_gates.json", json.dumps(gates, indent=2)
        )
        return AgentResult(
            result_id="r-verify",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
            evidence_refs=[s.source_id for s in self.sources],
            limitations=[f"{len(gates)} sources graded"],
        )

    def _synthesize(self, brief: AgentBrief) -> AgentResult:
        self._compute_standings()  # persiste standings/edges do run
        pack = build_evidence_pack("pack-1", self.claims, self.sources, self.spans)
        assembler = ReportAssembler(self.objective)
        body = "\n\n".join(
            f"- **{c.claim_id}** ({c.standing.value}, {c.confidence:.2f}) — {c.statement} [cite:{sp.source_id}]"
            for c in self.claims
            for sp in self.spans
            if sp.evidence_id in c.support_edges
        )
        assembler.add_section("Findings", body or "_no claims extracted_")
        self.report_text = assembler.assemble(self.sources)
        self.state.write_text("delivery/report.md", self.report_text)
        return AgentResult(
            result_id="r-synthesize",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
            evidence_refs=[sp.evidence_id for sp in self.spans],
            limitations=["synthesis is deterministic; no LLM writer attached"],
            declared_tests=[],
            executed_tests=[],
            payload={"pack_id": pack.pack_id, "claims": len(self.claims)},
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
) -> dict[str, Any]:
    """Run the full offline pipeline and return a JSON-serializable summary."""
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

    state, _manifest = prepare_run_dir(plan, contract, runs_root, run_id)
    result, executor = execute_plan(plan, contract, corpus, state)

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
        "exit_code": 0 if not result.failed else 1,
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
