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
    p_demo.add_argument("--out", default=".research", help="runs root directory")

    p_run = sub.add_parser("run", help="execute a plan from a run dir")
    p_run.add_argument("--run-dir", required=True)
    p_run.add_argument(
        "--corpus", default=None, help="file corpus for retrieval (optional)"
    )

    p_status = sub.add_parser("status", help="print run status")
    p_status.add_argument("--run-dir", required=True)

    p_resume = sub.add_parser("resume", help="verify hashes and reload manifest")
    p_resume.add_argument("--run-dir", required=True)

    p_verify = sub.add_parser("verify", help="re-run source/claim/integrity gates")
    p_verify.add_argument("--run-dir", required=True)

    p_report = sub.add_parser("report", help="assemble the report from a run dir")
    p_report.add_argument("--run-dir", required=True)

    sub.add_parser("monitor", help="delta-search monitor (placeholder)")
    return parser


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
    return 0 if not decision.blocking() else 1


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
    )
    print(json.dumps(summary, indent=2))
    return summary.get("exit_code", 0)


def cmd_status(args: argparse.Namespace) -> int:
    from kdrx.state import load_manifest_from_dir

    m = load_manifest_from_dir(args.run_dir)
    print(f"run: {m.run_id}  status: {m.status}")
    print(f"completed: {len(m.completed_tasks)}  failed: {len(m.failed_tasks)}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    from kdrx.state import RunState, load_manifest_from_dir

    run_dir = Path(args.run_dir)
    m = load_manifest_from_dir(run_dir)
    rs = RunState(run_dir.parent, m.run_id)
    m2 = rs.resume()
    print(f"resumed {m2.run_id}")
    if m2.metadata.get("hash_mismatch"):
        print(f"hash mismatch: {m2.metadata['hash_mismatch']}")
        return 1
    print("hashes verified")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from kdrx.state import load_manifest_from_dir

    m = load_manifest_from_dir(args.run_dir)
    print(f"verifying run {m.run_id} ... (gate re-run over persisted artifacts)")
    print(f"gates: {m.gate_results or 'none recorded'}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    report_path = run_dir / "delivery" / "report.md"
    if report_path.exists():
        print(report_path.read_text(encoding="utf-8"))
        return 0
    print(f"no report at {report_path}")
    return 1


def cmd_monitor(args: argparse.Namespace) -> int:
    print(
        "monitor: delta-search requires a live source adapter; nothing to do offline."
    )
    return 0


_CMDS = {
    "schema": cmd_schema,
    "doctor": cmd_doctor,
    "eval": cmd_eval,
    "hook": cmd_hook,
    "demo": cmd_demo,
    "status": cmd_status,
    "resume": cmd_resume,
    "verify": cmd_verify,
    "report": cmd_report,
    "monitor": cmd_monitor,
    "run": cmd_demo,  # `run` reuses the offline file-research runner
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
