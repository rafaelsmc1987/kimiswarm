"""``kdr`` command-line interface (plan §40: /kdr:plan, /kdr:run, ...).

The CLI is the deterministic entry point for the offline core: schema export,
doctor, hook dispatch, eval, and an end-to-end demo over a file corpus.
"""

from __future__ import annotations

import argparse
import json
import os
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
    p_eval.add_argument(
        "--split",
        choices=["gold", "dev", "heldout", "all"],
        default="all",
        help="T-09-05: which data split to evaluate (heldout = prova final)",
    )
    p_eval.add_argument(
        "--trials",
        type=int,
        default=1,
        help="T-09-07: number of trials per case (stability check)",
    )

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
    g_hook = p_hook.add_mutually_exclusive_group(required=True)
    g_hook.add_argument("--json", help="hook payload as JSON")
    g_hook.add_argument(
        "--stdin",
        action="store_true",
        help="read hook payload from stdin (harness exec form)",
    )

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
    g_obj = p_plan.add_mutually_exclusive_group(required=True)
    g_obj.add_argument("--objective", help="research objective (inline)")
    g_obj.add_argument(
        "--objective-file",
        help="read the objective from a UTF-8 file (no shell interpolation, D6)",
    )
    p_plan.add_argument("--corpus", default=None, help="file corpus dir (sizing only)")
    p_plan.add_argument("--out", default=".research/runs", help="runs root directory")
    p_plan.add_argument("--run-id", default=None)
    p_plan.add_argument(
        "--session-id",
        default=None,
        help="bind this Claude Code session to the run (env KDR_SESSION_ID)",
    )
    p_plan.add_argument("--json", action="store_true", help="emit JSON summary")

    p_import = sub.add_parser(
        "import-plan",
        help="validate + canonize + persist an enriched plan (canonical handoff, D1)",
    )
    p_import.add_argument("--run-dir", required=True)
    g_import = p_import.add_mutually_exclusive_group(required=True)
    g_import.add_argument(
        "--stdin", action="store_true", help="read plan JSON from stdin"
    )
    g_import.add_argument("--file", help="read plan JSON from a file")
    p_import.add_argument(
        "--dispositions-file",
        default=None,
        help="planner dispositions JSON (list[PlannerDisposition])",
    )
    p_import.add_argument(
        "--source",
        choices=["council-imported", "manual"],
        default="manual",
        help="provenance source of the import",
    )
    p_import.add_argument(
        "--review-approved",
        action="store_true",
        help="mark the import as council-review-approved (D3)",
    )
    p_import.add_argument("--json", action="store_true", help="emit JSON summary")

    p_run = sub.add_parser("run", help="execute a persisted plan (see `kdr plan`)")
    p_run.add_argument("--run-dir", required=True)
    p_run.add_argument(
        "--session-id",
        default=None,
        help="bind this Claude Code session to the run (env KDR_SESSION_ID)",
    )
    p_run.add_argument("--corpus", default=None, help="file corpus dir (offline path)")

    p_status = sub.add_parser("status", help="print run status")
    p_status.add_argument("--run-dir", required=True)
    p_status.add_argument("--json", action="store_true", help="emit JSON status")

    p_resume = sub.add_parser("resume", help="verify hashes and reload manifest")
    p_resume.add_argument("--run-dir", required=True)
    p_resume.add_argument(
        "--session-id",
        default=None,
        help="bind this Claude Code session to the run (env KDR_SESSION_ID)",
    )
    p_resume.add_argument(
        "--corpus", default=None, help="file corpus dir (offline path)"
    )

    p_verify = sub.add_parser("verify", help="re-run source/claim/integrity gates")
    p_verify.add_argument("--run-dir", required=True)

    p_seal = sub.add_parser(
        "seal", help="verify-then-seal: gates sobre os bytes finais + selo"
    )
    p_seal.add_argument("--run-dir", required=True)
    p_seal.add_argument("--json", action="store_true", help="emit JSON")

    p_report = sub.add_parser("report", help="assemble the report from a run dir")
    p_report.add_argument("--run-dir", required=True)

    p_monitor = sub.add_parser(
        "monitor",
        help="T-10-01: standing queries + delta-search sobre file corpus",
    )
    p_monitor.add_argument("--corpus", required=True, help="file corpus dir to watch")
    p_monitor.add_argument(
        "--state",
        default=".research/monitor-state.json",
        help="JSON state file with snapshots + saved queries",
    )
    p_monitor.add_argument(
        "--save-query", default=None, help="register a standing query (objective)"
    )
    p_monitor.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def _maybe_bind_session(
    args: argparse.Namespace, run_id: str, run_dir: Path, runs_root: str | Path
) -> None:
    """Binding explícito session_id -> run no registry (SW-00 D2.1)."""
    session_id = getattr(args, "session_id", None) or os.environ.get("KDR_SESSION_ID")
    if not session_id:
        return
    from kdrx.native_hooks import SessionRegistry

    SessionRegistry.for_runs_root(runs_root).bind(
        session_id,
        run_id=run_id,
        run_dir=str(Path(run_dir).resolve()),
        binding="explicit",
    )


def cmd_plan(args: argparse.Namespace) -> int:
    from kdrx.planner import plan_gate
    from kdrx.runner import build_contract, build_plan, prepare_run_dir

    objective = args.objective
    if args.objective_file:
        try:
            objective = Path(args.objective_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            print(f"error: objective file: {exc}", file=sys.stderr)
            return 2
        if not objective:
            print("error: objective file is empty", file=sys.stderr)
            return 2
    corpus_size = 0
    if args.corpus:
        from kdrx.retrieval import FileCorpus

        corpus_size = len(FileCorpus(args.corpus).scan())
    contract = build_contract(objective)
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
    _maybe_bind_session(args, manifest.run_id, state.run_dir, args.out)
    waves = sorted({t.wave for t in plan.tasks})
    summary = {
        "run_id": manifest.run_id,
        "run_dir": str(state.run_dir),
        "plan_id": plan.plan_id,
        "contract_id": contract.contract_id,
        "route": contract.route.value,
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


def cmd_import_plan(args: argparse.Namespace) -> int:
    """D1: validate-then-write import do plano enriquecido (canonical handoff).

    Exit codes: 0 ok · 1 gate estrutural/semântico · 2 usage/IO · 3
    JSON/pydantic/dispositions validation · 4 state conflict.
    """
    from pydantic import TypeAdapter, ValidationError

    from kdrx.planner import plan_gate
    from kdrx.runner import PlanImportError, import_plan_into_run
    from kdrx.schemas.plan import PlannerDisposition, ResearchPlan
    from kdrx.schemas.request import ResearchContract
    from kdrx.state import RunState, load_manifest_from_dir

    # 1. payload (stdin ou arquivo; grupo mutuamente exclusivo)
    if args.stdin:
        raw = sys.stdin.read()
    else:
        try:
            raw = Path(args.file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: plan file: {exc}", file=sys.stderr)
            return 2
    # 2. pydantic (JSON + extra="forbid") -> 3
    try:
        plan = ResearchPlan.model_validate_json(raw)
    except ValidationError as exc:
        print(f"error: invalid plan payload: {exc}", file=sys.stderr)
        return 3

    # 3. manifest + contract do run dir -> 2
    run_dir = Path(args.run_dir)
    manifest_path = run_dir / "manifest.json"
    contract_path = run_dir / "research_contract.json"
    if not manifest_path.exists() or not contract_path.exists():
        print(
            f"error: {run_dir} sem manifest.json/research_contract.json — "
            "crie o run com `kdr plan` primeiro",
            file=sys.stderr,
        )
        return 2
    try:
        manifest = load_manifest_from_dir(run_dir)
        contract = ResearchContract.model_validate_json(
            contract_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        print(f"error: contract ilegível: {exc}", file=sys.stderr)
        return 2

    # 9. dispositions (D5) -> 3 (shape inválida); arquivo ilegível -> 2
    dispositions = None
    if args.dispositions_file:
        try:
            raw_disp = Path(args.dispositions_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: dispositions file: {exc}", file=sys.stderr)
            return 2
        try:
            dispositions = TypeAdapter(list[PlannerDisposition]).validate_json(raw_disp)
        except ValidationError as exc:
            print(f"error: invalid dispositions: {exc}", file=sys.stderr)
            return 3

    if run_dir.name != manifest.run_id:
        print(f"error: run dir {run_dir} ≠ run_id do manifest", file=sys.stderr)
        return 2
    state = RunState(run_dir.parent, manifest.run_id)
    try:
        provenance = import_plan_into_run(
            state,
            plan,
            contract,
            source=args.source,
            review_approved=args.review_approved,
            dispositions=dispositions,
        )
    except PlanImportError as exc:
        print(f"error: import blocked: {exc}", file=sys.stderr)
        if exc.details:
            print(json.dumps(exc.details, indent=2, default=str), file=sys.stderr)
        return exc.exit_code

    # D7: warning não-bloqueante para task ids fora do executor offline
    known_ids = {"T-RETRIEVE", "T-VERIFY", "T-SYNTHESIZE", "T-INTEGRITY"}
    unknown = sorted({t.task_id for t in plan.tasks} - known_ids)
    if unknown:
        print(
            f"warning: task ids {unknown} não são executáveis pelo executor "
            "offline `kdr run`; use /kdr-x:kdr-run",
            file=sys.stderr,
        )

    gate = plan_gate(plan, contract)  # passa por construção (import já bloqueou)
    waves = sorted(plan.waves)
    summary = {
        "run_id": manifest.run_id,
        "run_dir": str(state.run_dir),
        "plan_hash": provenance["sha256"],
        "revision": provenance["revision"],
        "source": provenance["source"],
        "review_approved": provenance["review_approved"],
        "gate": gate.verdict.value,
        "tasks": [t.task_id for t in plan.tasks],
        "waves": waves,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"imported plan into {manifest.run_id} "
            f"(hash {provenance['sha256'][:12]}, rev {provenance['revision']})"
        )
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    from kdrx.schemas import export_json_schemas

    written = export_json_schemas(args.out)
    print(f"exported {len(written)} schemas to {args.out}")
    for name, path in written.items():
        print(f"  {name}: {path}")
    return 0


def _find_plugin_root() -> Path | None:
    """Localiza a raiz do plugin kdr-x (SW-01 D4).

    Ordem de busca: env ``KDRX_PLUGIN_ROOT`` -> env ``CLAUDE_PLUGIN_ROOT`` ->
    sobe a partir do cwd procurando ``plugins/kdr-x/.claude-plugin/plugin.json``
    (layout monorepo) ou ``.claude-plugin/plugin.json`` (plugin na raiz).
    Retorna ``None`` se nenhuma raiz com manifesto for encontrada.
    """
    for env_var in ("KDRX_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"):
        value = os.environ.get(env_var)
        if value:
            root = Path(value)
            if (root / ".claude-plugin" / "plugin.json").is_file():
                return root
    current = Path.cwd().resolve()
    for base in (current, *current.parents):
        for root in (base / "plugins" / "kdr-x", base):
            if (root / ".claude-plugin" / "plugin.json").is_file():
                return root
    return None


def _check_manifest_completeness(root: Path) -> list[str]:
    """Agents/commands/skills declarados no manifesto == disco (SW-01 D4).

    Paths declarados carregam prefixo ``./``, removido ao resolver contra a
    raiz do plugin. Retorna a lista de divergências (vazia = completo).
    """
    manifest = json.loads(
        (root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    problems: list[str] = []
    for field in ("agents", "commands", "skills"):
        declared = {p.removeprefix("./") for p in manifest.get(field, [])}
        field_dir = root / field
        if field == "skills":  # skills são diretórios; agents/commands são .md
            on_disk = (
                {f"skills/{d.name}" for d in field_dir.iterdir() if d.is_dir()}
                if field_dir.is_dir()
                else set()
            )
        else:
            on_disk = {f"{field}/{f.name}" for f in field_dir.glob("*.md")}
        for rel in sorted(on_disk - declared):
            problems.append(f"{rel} existe no disco mas não está declarado")
        for rel in sorted(declared - on_disk):
            problems.append(f"{rel} declarado mas ausente no disco")
    return problems


def _check_role_resolution_parity(root: Path) -> list[str]:
    """Paridade role-resolution <-> AgentRole <-> manifesto (SW-01 D4).

    As chaves de ``agents`` no role-resolution devem ser exatamente os valores
    do enum ``AgentRole`` (ambas as direções); todo alvo deve ter
    ``agents/<nome>.md`` existente; e todo ``agents/*.md`` deve estar
    declarado no manifesto. Retorna a lista de divergências (vazia = paridade).
    """
    from kdrx.schemas.enums import AgentRole

    resolution_path = root / "agents" / "role-resolution.json"
    if not resolution_path.is_file():
        return ["agents/role-resolution.json ausente"]
    resolution = json.loads(resolution_path.read_text(encoding="utf-8"))
    manifest = json.loads(
        (root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    problems: list[str] = []
    mapping = resolution.get("agents", {})
    enum_values = {role.value for role in AgentRole}
    for role in sorted(set(mapping) - enum_values):
        problems.append(f"{role} não é um AgentRole")
    for role in sorted(enum_values - set(mapping)):
        problems.append(f"AgentRole {role} sem mapeamento")
    for role, target in sorted(mapping.items()):
        if not (root / "agents" / f"{target}.md").is_file():
            problems.append(f"alvo de {role} (agents/{target}.md) inexistente")
    declared = {p.removeprefix("./") for p in manifest.get("agents", [])}
    for agent_file in sorted((root / "agents").glob("*.md")):
        if f"agents/{agent_file.name}" not in declared:
            problems.append(f"agents/{agent_file.name} não declarado no manifesto")
    return problems


def _check_research_writable() -> str | None:
    """Probe de escrita em ``.research`` sob o cwd (SW-01 D4).

    Cria o diretório, escreve um arquivo temporário e o remove; qualquer run
    precisa desse acesso. Retorna a mensagem de erro (``None`` = writable).
    """
    probe_dir = Path.cwd() / ".research"
    probe_file = probe_dir / ".doctor-write-probe"
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
    except OSError as exc:
        return str(exc)
    return None


def cmd_doctor(args: argparse.Namespace) -> int:
    import kdrx
    import pydantic
    from kdrx.schemas import SCHEMAS

    failures = 0
    print(f"kdr {kdrx.__version__}")
    # SW-01 D4: origem do import + versão do pydantic (skew observável)
    print(f"kdrx importable: {kdrx.__file__}")
    print(f"pydantic {pydantic.__version__}")
    print(f"schemas: {len(SCHEMAS)} canonical models")
    for name in SCHEMAS:
        print(f"  - {name}")

    # SW-01 D4: checks de saúde do plugin; sem plugin root, WARN e pula 3-4
    plugin_root = _find_plugin_root()
    if plugin_root is None:
        print(
            "plugin manifest: WARN (plugin root não encontrado; "
            "checks de manifesto e paridade pulados)"
        )
    else:
        problems = _check_manifest_completeness(plugin_root)
        if problems:
            failures += 1
            print("plugin manifest: FAIL")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print("plugin manifest: PASS")
        problems = _check_role_resolution_parity(plugin_root)
        if problems:
            failures += 1
            print("role-resolution parity: FAIL")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print("role-resolution parity: PASS")

    writable = _check_research_writable()
    if writable is not None:
        failures += 1
        print(f".research writable: FAIL ({writable})")
    else:
        print(".research writable: PASS")

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
    if not ok:
        failures += 1
    return 1 if failures else 0


def cmd_hook(args: argparse.Namespace) -> int:
    from kdrx.hooks import (
        hook_pre_tool_use,
        hook_stop,
        hook_subagent_stop,
        hook_task_completed,
        hook_task_created,
    )
    from kdrx.schemas.plan import AgentResult, TaskSpec

    if args.stdin:
        from kdrx.hook_dispatch import main as _dispatch

        return _dispatch([args.name])
    payload = json.loads(args.json)
    if args.name == "pre_tool_use":
        decision = hook_pre_tool_use(
            payload["tool_name"],
            payload.get("tool_input", {}),
            run_root=payload.get("run_root"),
            authorized_tools=payload.get("authorized_tools"),
            sealed_paths=payload.get("sealed_paths"),
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
            verified_report_hash_match=payload.get("verified_report_hash_match"),
        )
    else:  # pragma: no cover - argparse restricts choices
        raise SystemExit(f"unknown hook {args.name}")

    print(decision.model_dump_json(indent=2))
    # Claude Code hook convention: 0 = allow, 2 = block with feedback.
    return 2 if decision.blocking() else 0


def cmd_eval(args: argparse.Namespace) -> int:
    from kdrx.evals import EvalHarness, builtin_cases, run_multi_trial

    harness = EvalHarness()
    for case in builtin_cases(split=None if args.split == "all" else args.split):
        harness.register(case)
    trials = max(1, int(getattr(args, "trials", 1)))
    if trials > 1:
        # T-09-07: multi-trial; gate corre sobre a primeira trial
        # (detectores determinísticos => trials estáveis; instabilidade é bug).
        results = run_multi_trial(harness.cases, trials)
        reports = [r.trials[0] for r in results]
        unstable = [r.case_id for r in results if not r.stable]
    else:
        results = []
        reports = harness.run_all()
        unstable = []
    gate = harness.regression_gate(reports)
    if args.json:
        print(
            json.dumps(
                {
                    "split": args.split,
                    "trials": trials,
                    "unstable_cases": unstable,
                    "gate": {
                        "passed": gate.passed,
                        "reasons": gate.reasons,
                        "threshold_version": gate.threshold_version,
                        "metrics": {
                            k: {
                                "recall": round(m.recall, 4),
                                "precision": round(m.precision, 4),
                                "f1": round(m.f1, 4),
                                "calibration": round(m.calibration, 4),
                                "expected": m.expected,
                                "detected": m.detected,
                            }
                            for k, m in gate.metrics.items()
                            if m.expected or m.detected
                        },
                    },
                    "reports": [r.__dict__ for r in reports],
                },
                indent=2,
                default=str,
            )
        )
    else:
        for r in reports:
            print(r.summary())
            for d in r.details:
                print(f"    {d}")
        if trials > 1:
            labels = ", ".join(unstable) if unstable else "none"
            print(f"trials: {trials} (unstable cases: {labels})")
        print(gate.summary())
    return 0 if gate.passed else 1


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
    # D8: scaffold sem import continua permitido; nota não-bloqueante
    if (manifest.metadata.get("plan") or {}).get("source") == "scaffold-default":
        print(
            "note: running scaffold-default plan (no council import)",
            file=sys.stderr,
        )
    _maybe_bind_session(args, manifest.run_id, run_dir, run_dir.parent)
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
    from kdrx.state import hash_file, load_manifest_from_dir

    m = load_manifest_from_dir(args.run_dir)
    plan_meta = m.metadata.get("plan")
    if args.json:
        plan_blob = dict(plan_meta) if isinstance(plan_meta, dict) else {}
        stored = plan_blob.get("sha256")
        plan_path = Path(args.run_dir) / "plan.json"
        plan_blob["plan_hash_match"] = bool(
            stored and plan_path.is_file() and hash_file(plan_path) == stored
        )
        print(
            json.dumps(
                {
                    "run_id": m.run_id,
                    "status": m.status.value,
                    "completed": m.completed_tasks,
                    "failed": m.failed_tasks,
                    "plan": plan_blob,
                },
                indent=2,
            )
        )
    else:
        print(f"run: {m.run_id}  status: {m.status}")
        print(f"completed: {len(m.completed_tasks)}  failed: {len(m.failed_tasks)}")
        if isinstance(plan_meta, dict) and plan_meta.get("sha256"):
            print(
                f"plan: {plan_meta['sha256'][:12]} "
                f"({plan_meta.get('source', 'unknown')}, "
                f"rev {plan_meta.get('revision', 0)}, "
                f"approved={plan_meta.get('review_approved', False)})"
            )
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
    _maybe_bind_session(args, m.run_id, run_dir, run_dir.parent)
    m = rs.resume()
    if m.metadata.get("hash_mismatch"):
        print(
            f"hash mismatch detectado: {m.metadata['hash_mismatch']}", file=sys.stderr
        )
        print("run não retomado (provenance comprometida)", file=sys.stderr)
        return 2
    # SW-02: plan gate antes de retomar (fecha o gap do split-brain, D1.8)
    from pydantic import ValidationError

    from kdrx.planner import plan_gate
    from kdrx.schemas.plan import ResearchPlan
    from kdrx.schemas.request import ResearchContract

    try:
        plan = ResearchPlan.model_validate_json(
            (run_dir / "plan.json").read_text(encoding="utf-8")
        )
        contract = ResearchContract.model_validate_json(
            (run_dir / "research_contract.json").read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        print(f"error: plano/contrato corrompido: {exc}", file=sys.stderr)
        return 1
    gate = plan_gate(plan, contract)
    if gate.blocking():
        print("plan gate BLOCKED:", file=sys.stderr)
        for reason in gate.blocking_reasons:
            print(f"  - {reason}", file=sys.stderr)
        return 1
    corpus_arg = getattr(args, "corpus", None)
    if not corpus_arg:
        print(
            "error: resume offline exige --corpus <dir> (executor R4)", file=sys.stderr
        )
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
    # SW-02: recheck do plano/DAG persistido (informativo; all_pass não muda)
    plan_dag = "fail"
    plan_p = run_dir / "plan.json"
    if plan_p.exists():
        from pydantic import ValidationError

        from kdrx.dag import compile_dag
        from kdrx.schemas.plan import ResearchPlan

        try:
            persisted_plan = ResearchPlan.model_validate_json(
                plan_p.read_text(encoding="utf-8")
            )
            plan_dag = "pass" if compile_dag(persisted_plan.tasks).is_valid else "fail"
        except (OSError, ValidationError):
            plan_dag = "fail"
    results = {
        "source_trust": "pass" if src_pass else "fail",
        "citation_integrity": citation.verdict.value,
        "security": security.verdict.value,
        "plan_dag": plan_dag,
    }
    print(json.dumps(results, indent=2))
    all_pass = (
        src_pass
        and citation.verdict == GateVerdict.PASS
        and security.verdict == GateVerdict.PASS
    )
    print(f"verify: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


def cmd_seal(args: argparse.Namespace) -> int:
    """D1: verify-then-seal determinístico sobre os bytes finais do report.

    Exit codes: 0 selado · 1 gate falhou (verdicts persistidos, selo NÃO
    escrito) · 2 usage/IO (manifest/plan/report/sources ausentes) · 3 pydantic
    (plan.json corrompido).
    """
    from datetime import datetime, timezone

    from pydantic import ValidationError

    from kdrx.reporting import citation_integrity_gate
    from kdrx.runner import (
        _sealable_hashes,
        seal_delivery,
        unresolved_critical_claims,
    )
    from kdrx.schemas.claims import Claim
    from kdrx.schemas.corpus import EvidenceSpan, SourceRecord
    from kdrx.schemas.enums import GateVerdict
    from kdrx.schemas.plan import ResearchPlan
    from kdrx.security import security_gate
    from kdrx.state import RunState, hash_bytes, load_manifest_from_dir
    from kdrx.verification import source_trust_gate

    run_dir = Path(args.run_dir)

    # 1-2. manifest.json (existência + shape) -> 2
    try:
        manifest = load_manifest_from_dir(run_dir)
    except (OSError, ValidationError) as exc:
        print(f"error: manifest.json ausente/corrompido: {exc}", file=sys.stderr)
        return 2

    # 3. plan.json: ausente -> 2; ValidationError -> 3
    plan_p = run_dir / "plan.json"
    if not plan_p.exists():
        print(
            f"error: {run_dir} sem plan.json — crie o run com `kdr plan` primeiro",
            file=sys.stderr,
        )
        return 2
    try:
        plan = ResearchPlan.model_validate_json(plan_p.read_text(encoding="utf-8"))
    except ValidationError as exc:
        print(f"error: plan.json corrompido: {exc}", file=sys.stderr)
        return 3

    # 4. compile_dag: inválido conta como gate fail (não usage error)
    from kdrx.dag import compile_dag

    dag_ok = compile_dag(plan.tasks).is_valid
    plan_dag = "pass" if dag_ok else "fail"

    # 5. corpus/evidence/claims: ausentes -> 2 (parity cmd_verify); claims vazio ok
    def _jsonl(path: Path, model: type) -> list:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            print(f"error: falha ao ler {path}: {exc}", file=sys.stderr)
            raise SystemExit(2)
        out = []
        for num, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                out.append(model.model_validate_json(line))
            except (ValidationError, json.JSONDecodeError) as exc:
                print(
                    f"error: {path.name} linha {num} corrompida: {exc}",
                    file=sys.stderr,
                )
                raise SystemExit(2)
        return out

    sources_p = run_dir / "corpus" / "sources.jsonl"
    spans_p = run_dir / "evidence" / "spans.jsonl"
    claims_p = run_dir / "claims" / "claims.jsonl"
    missing = [str(p) for p in (sources_p, spans_p, claims_p) if not p.exists()]
    if missing:
        print(
            f"error: artifacts ausentes {missing} — execute `kdr run`/workflow primeiro",
            file=sys.stderr,
        )
        return 2
    sources = _jsonl(sources_p, SourceRecord)
    spans = _jsonl(spans_p, EvidenceSpan)
    claims = _jsonl(claims_p, Claim)

    # 6. report.md em BYTES (CRLF-safe); ausente/ilegível -> 2
    report_p = run_dir / "delivery" / "report.md"
    if not report_p.exists():
        print(
            f"error: sem relatório em {report_p} — o selo hasheia os bytes finais",
            file=sys.stderr,
        )
        return 2
    try:
        report_bytes = report_p.read_bytes()
        report_text = report_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: report ilegível: {exc}", file=sys.stderr)
        return 2
    report_hash = hash_bytes(report_bytes)

    # 7. Gates canônicos sobre os bytes finais
    src_pass = bool(sources) and all(
        g.verdict == GateVerdict.PASS for g in (source_trust_gate(s) for s in sources)
    )
    citation = citation_integrity_gate(
        report_text, sources=sources, claims=claims, spans=spans
    )
    security = security_gate(run_dir)
    gate_results = {
        "source_trust": "pass" if src_pass else "fail",
        "citation_integrity": citation.verdict.value,
        "security": security.verdict.value,
        "plan_dag": plan_dag,
    }

    # 8. Verdicts persistidos SEMPRE (trilha de auditoria; validate-then-write:
    # o que NÃO se escreve em fail é o SELO — passos 10-11)
    state = RunState(run_dir.parent, run_dir.name)
    gate_ts = datetime.now(timezone.utc).isoformat()
    integrity_ok = src_pass and citation.verdict == GateVerdict.PASS and dag_ok
    state.write_text(
        "verification/integrity.json",
        json.dumps(
            {
                "verdict": "pass" if integrity_ok else "fail",
                "source_trust": "pass" if src_pass else "fail",
                "citation_integrity": citation.verdict.value,
                "plan_dag": plan_dag,
                "timestamp": gate_ts,
            },
            indent=2,
        ),
    )
    state.write_text(
        "verification/security.json",
        json.dumps({"verdict": security.verdict.value, "timestamp": gate_ts}, indent=2),
    )

    all_pass = integrity_ok and security.verdict == GateVerdict.PASS
    if not all_pass:
        blocking_reasons: list[str] = []
        if not src_pass:
            blocking_reasons.append(
                "source_trust: nem todas as fontes passaram no trust gate"
            )
        blocking_reasons.extend(citation.blocking_reasons)
        blocking_reasons.extend(security.blocking_reasons)
        if not dag_ok:
            blocking_reasons.append("plan_dag: plan.json não compila")
        out = {
            "verdict": "fail",
            "sealed": False,
            "verified_report_hash": None,
            "gate_results": gate_results,
            "blocking_reasons": blocking_reasons,
        }
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(json.dumps(out, indent=2))
            print("seal: FAIL")
        return 1

    # 10. Selo (validate-then-write: todos os gates passaram)
    sealed_at = datetime.now(timezone.utc).isoformat()
    previous = manifest.metadata.get("seal") or {}
    revision = int(previous.get("revision", 0)) + 1
    manifest.artifact_hashes = _sealable_hashes(state)
    manifest.gate_results = {"integrity": "pass", "security": "pass"}
    manifest.metadata["seal"] = {
        "verified_report_hash": report_hash,
        "sealed_at": sealed_at,
        "revision": revision,
    }
    state.save_manifest(manifest)
    unresolved = unresolved_critical_claims(run_dir)
    dm = seal_delivery(
        state,
        manifest,
        produced_by="kdr:seal",
        gate_timestamps={
            "source_trust": gate_ts,
            "citation_integrity": gate_ts,
            "security": gate_ts,
            "plan_dag": gate_ts,
            "sealed_at": sealed_at,
        },
        unresolved_critical=unresolved,
    )
    state.append_event(
        {
            "kind": "delivery_sealed",
            "run_id": manifest.run_id,
            "verified_report_hash": report_hash,
            "sealed_at": sealed_at,
        }
    )
    if unresolved:
        print(
            f"warning: {len(unresolved)} claim(s) CRITICAL não resolvida(s) — "
            "kdr seal atesta hash/gates; a resolução de claims críticas "
            "permanece gate do Stop hook (CRITICAL_RESOLVED)",
            file=sys.stderr,
        )

    # 11. stdout JSON -> exit 0
    out = {
        "verdict": "pass",
        "sealed": True,
        "run_dir": str(run_dir),
        "verified_report_hash": report_hash,
        "delivered_at": dm.delivered_at.isoformat() if dm.delivered_at else None,
        "gate_timestamps": dm.gate_timestamps,
    }
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(json.dumps(out, indent=2))
        print("seal: PASS")
    return 0


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
    """T-10-01: delta-search sobre file corpus + saved queries.

    Mantém ``{snapshots: {corpus: {arquivo: hash}}, queries: [...]}`` no state
    JSON; a cada chamada detecta fontes novas/alteradas/removidas e (opcional)
    registra uma standing query par o delta-search futuro.
    """
    from datetime import datetime, timezone

    from kdrx.retrieval import delta_sources, snapshot_corpus_hashes

    state_path = Path(args.state)
    state = {"snapshots": {}, "queries": []}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    corpus_key = str(args.corpus)

    current = snapshot_corpus_hashes(args.corpus)
    previous = state["snapshots"].get(corpus_key, {})
    delta = delta_sources(previous, current)
    state["snapshots"][corpus_key] = current

    if args.save_query:
        entries = state["queries"]
        if not any(
            q["query"] == args.save_query and q["corpus_dir"] == corpus_key
            for q in entries
        ):
            entries.append(
                {
                    "query": args.save_query,
                    "corpus_dir": corpus_key,
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    out = {
        "corpus": corpus_key,
        "state_file": str(state_path),
        "tracked_files": len(current),
        "saved_queries": len(state["queries"]),
        **delta.as_dict(),
    }
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"monitor: {out['tracked_files']} tracked files in {corpus_key}")
        print(
            f"  added={out['added']} changed={out['changed']} removed={out['removed']}"
        )
        print(f"  saved queries: {out['saved_queries']} (state: {state_path})")
        if not delta.has_delta:
            print("  no delta since last snapshot")
    return 0


_CMDS = {
    "schema": cmd_schema,
    "doctor": cmd_doctor,
    "eval": cmd_eval,
    "hook": cmd_hook,
    "demo": cmd_demo,
    "plan": cmd_plan,
    "import-plan": cmd_import_plan,
    "status": cmd_status,
    "resume": cmd_resume,
    "verify": cmd_verify,
    "seal": cmd_seal,
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
