"""``kdr`` command-line interface (plan §40: /kdr:plan, /kdr:run, ...).

The CLI is the deterministic entry point for the offline core: schema export,
doctor, hook dispatch, eval, and an end-to-end demo over a file corpus.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from kdrx import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kdr",
        description="KDR-X — KimiSwarm Deep Research eXtended (deterministic core)",
    )
    parser.add_argument("--version", action="version", version=f"kdr {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("schema", help="export canonical JSON schemas").add_argument(
        "--out", default="plugins/kdr-x/schemas", help="output directory"
    )

    sub.add_parser("doctor", help="self-check imports, schemas and a smoke run")

    p_eval = sub.add_parser("eval", help="run the seeded-defect eval harness")
    p_eval.add_argument("--json", action="store_true", help="emit JSON")

    p_hook = sub.add_parser("hook", help="dispatch a deterministic hook")
    p_hook.add_argument(
        "name",
        choices=[
            "task_created",
            "pre_tool_use",
            "subagent_stop",
            "task_completed",
            "stop",
        ],
    )
    p_hook.add_argument("--json", required=True, help="hook payload as JSON")

    p_demo = sub.add_parser("demo", help="end-to-end offline demo over a file corpus")
    p_demo.add_argument("--corpus", required=True, help="directory of text files")
    p_demo.add_argument(
        "--objective", default="What does this corpus say?", help="research objective"
    )
    p_demo.add_argument("--out", default=".research/runs", help="runs root directory")
    p_demo.add_argument(
        "--live",
        action="store_true",
        help="enable live DOI resolution in the source trust gate (needs network)",
    )

    p_plan = sub.add_parser(
        "plan", help="create contract + plan, run plan gate, scaffold run dir"
    )
    p_plan.add_argument("--objective", required=True)
    p_plan.add_argument("--corpus", default=None, help="file corpus dir (sizing only)")
    p_plan.add_argument("--out", default=".research/runs", help="runs root directory")
    p_plan.add_argument("--run-id", default=None)
    p_plan.add_argument("--json", action="store_true", help="emit JSON summary")

    p_run = sub.add_parser("run", help="execute a persisted plan (see `kdr plan`)")
    p_run.add_argument("--run-dir", required=True)
    p_run.add_argument("--corpus", default=None, help="file corpus dir (offline path)")

    p_status = sub.add_parser("status", help="print run status")
    p_status.add_argument("--run-dir", required=True)

    p_resume = sub.add_parser("resume", help="verify hashes and reload manifest")
    p_resume.add_argument("--run-dir", required=True)
    p_resume.add_argument("--corpus", default=None, help="file corpus dir (offline path)")

    p_verify = sub.add_parser("verify", help="re-run source/claim/integrity gates")
    p_verify.add_argument("--run-dir", required=True)

    p_report = sub.add_parser("report", help="assemble the report from a run dir")
    p_report.add_argument("--run-dir", required=True)

    sub.add_parser("monitor", help="delta-search monitor (R12: not in offline core)")
    return parser


def cmd_plan(args: argparse.Namespace) -> int:
    from kdrx.planner import plan_gate
    from kdrx.runner import build_contract, build_plan, prepare_run_dir

    corpus_size = 0
    if args.corpus:
        from kdrx.retrieval import FileCorpus

        corpus_size = len(FileCorpus(args.corpus).scan())
    contract = build_contract(args.objective)
    plan = build_plan(contract, corpus_size)
    gate = plan_gate(plan, contract)
    if gate.blocking():
        print("plan gate BLOCKED:", file=sys.stderr)
        for reason in gate.blocking_reasons:
            print(f"  - {reason}", file=sys.stderr)
        return 1
    state, manifest = prepare_run_dir(
        plan, contract, runs_root=args.out, run_id=args.run_id
    )
    waves = sorted({t.wave for t in plan.tasks})
    summary = {
        "run_id": manifest.run_id,
        "run_dir": str(state.run_dir),
        "gate": gate.verdict.value,
        "tasks": [t.task_id for t in plan.tasks],
        "waves": waves,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"run_id: {manifest.run_id}")
        print(f"run_dir: {state.run_dir}")
        print(f"plan gate: {gate.verdict.value}")
        print(f"tasks: {len(plan.tasks)}  waves: {waves}")
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    from kdrx.schemas import export_json_schemas

    written = export_json_schemas(args.out)
    print(f"exported {len(written)} schemas to {args.out}")
    for name, path in written.items():
        print(f"  {name}: {path}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    import kdrx
    from kdrx.schemas import SCHEMAS

    print(f"kdr {kdrx.__version__}")
    print(f"schemas: {len(SCHEMAS)} canonical models")
    for name in SCHEMAS:
        print(f"  - {name}")
    # smoke run of the scheduler with a trivial DAG
    from kdrx.dag import compile_dag
    from kdrx.scheduler import WaveScheduler
    from kdrx.schemas.plan import (
        AcceptanceCriteria,
        AgentResult,
        Budget,
        RetryPolicy,
        TaskSpec,
    )
    from kdrx.schemas.enums import AgentRole, TaskStage

    tasks = [
        TaskSpec(
            task_id="T0",
            stage=TaskStage.RETRIEVAL,
            wave=0,
            role=AgentRole.WEB_EXPLORER,
            mission="smoke",
            outputs=["o0"],
            acceptance=AcceptanceCriteria(criteria=["ok"], output_schema="x"),
            retry_policy=RetryPolicy(max_retries=0),
            budget=Budget(tokens=1),
        )
    ]
    dag = compile_dag(tasks)

    def executor(brief: Any) -> AgentResult:
        return AgentResult(
            result_id="r",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
        )

    res = WaveScheduler(executor).run(dag)
    ok = dag.is_valid and not res.failed and res.completed == ["T0"]
    print(f"scheduler smoke: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def cmd_hook(args: argparse.Namespace) -> int:
    from kdrx.hooks import (
        hook_pre_tool_use,
        hook_stop,
        hook_subagent_stop,
        hook_task_completed,
        hook_task_created,
    )
    from kdrx.schemas.plan import AgentResult, TaskSpec

    payload = json.loads(args.json)
    if args.name == "pre_tool_use":
        decision = hook_pre_tool_use(
            payload["tool_name"],
            payload.get("tool_input", {}),
            run_root=payload.get("run_root"),
            authorized_tools=payload.get("authorized_tools"),
        )
    elif args.name == "task_created":
        decision = hook_task_created(TaskSpec.model_validate(payload["task"]))
    elif args.name == "subagent_stop":
        decision = hook_subagent_stop(
            AgentResult.model_validate(payload["result"]),
            TaskSpec.model_validate(payload["task"]),
        )
    elif args.name == "task_completed":
        decision = hook_task_completed(
            TaskSpec.model_validate(payload["task"]),
            AgentResult.model_validate(payload["result"]),
        )
    elif args.name == "stop":
        from kdrx.dag import compile_dag
        from kdrx.schemas.artifact import DeliveryManifest
        from kdrx.schemas.plan import TaskSpec as _T

        dag = compile_dag([_T.model_validate(t) for t in payload["tasks"]])
        decision = hook_stop(
            dag=dag,
            delivery=DeliveryManifest.model_validate(payload["delivery"]),
            integrity_pass=payload.get("integrity_pass", False),
            secret_scan_clean=payload.get("secret_scan_clean", False),
            artifact_open_test=payload.get("artifact_open_test", False),
            unresolved_critical=payload.get("unresolved_critical", []),
        )
    else:  # pragma: no cover - argparse restricts choices
        raise SystemExit(f"unknown hook {args.name}")

    print(decision.model_dump_json(indent=2))
    # Claude Code hook convention: 0 = allow, 2 = block with feedback.
    return 2 if decision.blocking() else 0


def cmd_eval(args: argparse.Namespace) -> int:
    from kdrx.evals import builtin_cases, EvalHarness

    harness = EvalHarness()
    for case in builtin_cases():
        harness.register(case)
    reports = harness.run_all()
    if args.json:
        print(json.dumps([r.__dict__ for r in reports], indent=2, default=str))
    else:
        for r in reports:
            print(r.summary())
            for d in r.details:
                print(f"    {d}")
        print(f"regression pass: {harness.regression_pass(reports)}")
    return 0 if harness.regression_pass(reports) else 1


def cmd_demo(args: argparse.Namespace) -> int:
    from kdrx.runner import run_file_research

    summary = run_file_research(
        corpus_dir=args.corpus,
        objective=args.objective,
        runs_root=args.out,
        live=args.live,
    )
    print(json.dumps(summary, indent=2))
    return summary.get("exit_code", 0)


def cmd_run(args: argparse.Namespace) -> int:
    from kdrx.planner import plan_gate
    from kdrx.retrieval import FileCorpus
    from kdrx.runner import execute_plan
    from kdrx.schemas.plan import ResearchPlan
    from kdrx.schemas.request import ResearchContract
    from kdrx.state import RunState, load_manifest_from_dir

    run_dir = Path(args.run_dir)
    plan_path = run_dir / "plan.json"
    contract_path = run_dir / "research_contract.json"
    if not plan_path.exists() or not contract_path.exists():
        print(
            f"error: {run_dir} sem plan.json/research_contract.json — "
            "crie o plano com `kdr plan` primeiro",
            file=sys.stderr,
        )
        return 2
    plan = ResearchPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    contract = ResearchContract.model_validate_json(
        contract_path.read_text(encoding="utf-8")
    )
    gate = plan_gate(plan, contract)
    if gate.blocking():
        print("plan gate BLOCKED:", file=sys.stderr)
        for reason in gate.blocking_reasons:
            print(f"  - {reason}", file=sys.stderr)
        return 1
    if not args.corpus:
        print(
            "error: --corpus é obrigatório no caminho offline (R3/R4)", file=sys.stderr
        )
        return 2
    manifest = load_manifest_from_dir(run_dir)
    state = RunState(run_dir.parent, manifest.run_id)
    corpus = FileCorpus(args.corpus)
    docs = corpus.scan()
    result, executor = execute_plan(plan, contract, corpus, state)
    summary = {
        "run_id": manifest.run_id,
        "documents": len(docs),
        "sources": len(executor.sources),
        "spans": len(executor.spans),
        "completed_tasks": result.completed,
        "failed_tasks": result.failed,
        "report": str(state.run_dir / "delivery" / "report.md"),
    }
    print(json.dumps(summary, indent=2))
    return 0 if not result.failed else 1


def cmd_status(args: argparse.Namespace) -> int:
    from kdrx.state import load_manifest_from_dir

    m = load_manifest_from_dir(args.run_dir)
    print(f"run: {m.run_id}  status: {m.status}")
    print(f"completed: {len(m.completed_tasks)}  failed: {len(m.failed_tasks)}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume real (T-04-04): verifica hashes e CONTINUA o DAG pendente."""
    from kdrx.runner import resume_run
    from kdrx.state import RunState, load_manifest_from_dir

    run_dir = Path(args.run_dir)
    try:
        m = load_manifest_from_dir(run_dir)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rs = RunState(run_dir.parent, m.run_id)
    m = rs.resume()
    if m.metadata.get("hash_mismatch"):
        print(f"hash mismatch detectado: {m.metadata['hash_mismatch']}", file=sys.stderr)
        print("run não retomado (provenance comprometida)", file=sys.stderr)
        return 2
    corpus_arg = getattr(args, "corpus", None)
    if not corpus_arg:
        print("error: resume offline exige --corpus <dir> (executor R4)", file=sys.stderr)
        return 2
    from kdrx.retrieval import FileCorpus

    corpus = FileCorpus(corpus_arg)
    result, _ex = resume_run(rs, corpus)
    print(f"resumed {m.run_id}: completed={result.completed} failed={result.failed}")
    return 0 if not result.failed else 1


def cmd_verify(args: argparse.Namespace) -> int:
    """Re-run source/claim/integrity gates over persisted run artifacts."""
    from kdrx.reporting import citation_integrity_gate
    from kdrx.schemas.claims import Claim
    from kdrx.schemas.corpus import EvidenceSpan, SourceRecord
    from kdrx.security import security_gate
    from kdrx.verification import source_trust_gate

    run_dir = Path(args.run_dir)

    def _jsonl(path: Path, model: type) -> list:
        return [
            model.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    sources_p = run_dir / "corpus" / "sources.jsonl"
    spans_p = run_dir / "evidence" / "spans.jsonl"
    claims_p = run_dir / "claims" / "claims.jsonl"
    missing = [str(p) for p in (sources_p, spans_p) if not p.exists()]
    if missing:
        print(
            f"error: artifacts ausentes {missing} — execute `kdr run` primeiro",
            file=sys.stderr,
        )
        return 2
    sources = _jsonl(sources_p, SourceRecord)
    spans = _jsonl(spans_p, EvidenceSpan)
    claims = _jsonl(claims_p, Claim) if claims_p.exists() else []

    # B-06/T-04-07: empty corpus NÃO retorna sucesso (existência é blocking).
    # E WARN não conta como PASS no E2E — delivery limpo exige verdict "pass".
    from kdrx.schemas.enums import GateVerdict

    src_pass = bool(sources) and all(
        g.verdict == GateVerdict.PASS for g in (source_trust_gate(s) for s in sources)
    )
    report_p = run_dir / "delivery" / "report.md"
    if report_p.exists():
        report_text = report_p.read_text(encoding="utf-8")
    else:
        report_text = ""
        print("warning: delivery/report.md ausente — citation gate sobre texto vazio")
    citation = citation_integrity_gate(
        report_text, sources=sources, claims=claims, spans=spans
    )
    security = security_gate(run_dir)
    results = {
        "source_trust": "pass" if src_pass else "fail",
        "citation_integrity": citation.verdict.value,
        "security": security.verdict.value,
    }
    print(json.dumps(results, indent=2))
    all_pass = (
        src_pass
        and citation.verdict == GateVerdict.PASS
        and security.verdict == GateVerdict.PASS
    )
    print(f"verify: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


def cmd_report(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    report_path = run_dir / "delivery" / "report.md"
    if not report_path.exists():
        print(
            f"error: sem relatório em {report_path} — "
            "execute `kdr run --run-dir <dir>` primeiro",
            file=sys.stderr,
        )
        return 1
    print(report_path.read_text(encoding="utf-8"))
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    """Delta-search (R12) is out of the offline core — explicit fail (FASE 8)."""
    print(
        "monitor: delta-search requer adapter de fonte live (rota R12) — "
        "não implementado no core offline; ver FASE 8 do plano de correção.",
        file=sys.stderr,
    )
    return 3


_CMDS = {
    "schema": cmd_schema,
    "doctor": cmd_doctor,
    "eval": cmd_eval,
    "hook": cmd_hook,
    "demo": cmd_demo,
    "plan": cmd_plan,
    "status": cmd_status,
    "resume": cmd_resume,
    "verify": cmd_verify,
    "report": cmd_report,
    "monitor": cmd_monitor,
    "run": cmd_run,  # executa ResearchPlan persistido (T-01-06); demo = atalho one-shot
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = _CMDS.get(args.command)
    if handler is None:  # pragma: no cover - argparse handles this
        parser.error(f"unknown command {args.command}")
    try:
        return handler(args)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
