"""Hooks nativos do Claude Code: envelopes, session registry e adapters (SW-00).

Os payloads oficiais (TaskCreated, TaskCompleted, SubagentStop, Stop,
PreToolUse) chegam pelo dispatcher ``plugins/kdr-x/hooks/kdr-hook`` e são
roteados para :func:`dispatch`. Os envelopes são tolerantes
(``extra="allow"``, todos os campos opcionais, leitura por atributo default —
nunca ``[]``), então nenhum payload nativo gera ``KeyError`` (D3/D5). A
resolução ``session_id -> run`` usa um registry persistente único em
``.research/session-registry.json`` (D1), com binding explícito via CLI
(``kdr plan|run|resume --session-id``) ou lazy pela regra do run ativo único
(D2). As assinaturas de ``kdrx.hooks`` ficam 100% estáveis: os adapters só
preparam insumos e chamam as funções existentes (D5).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from kdrx.dag import compile_dag
from kdrx.hooks import (
    hook_pre_tool_use,
    hook_stop,
    hook_subagent_stop,
    hook_task_completed,
    hook_task_created,
)
from kdrx.schemas.artifact import DeliveryManifest
from kdrx.schemas.claims import Claim
from kdrx.schemas.enums import ClaimImportance, GateKind, Standing, TaskStatus
from kdrx.schemas.gate import GateCheck, GateDecision
from kdrx.schemas.plan import AgentResult, ResearchPlan, RunManifest, TaskSpec
from kdrx.state import RunState


# --------------------------------------------------------------------------- #
# Envelopes nativos (payloads oficiais — code.claude.com/docs/en/hooks)
# --------------------------------------------------------------------------- #
class NativeHookEnvelope(BaseModel):
    """Base dos payloads nativos: ``extra="allow"`` (payloads evoluem) e
    todos os campos opcionais — parsing nunca levanta por campo ausente."""

    model_config = ConfigDict(extra="allow")

    session_id: str | None = None
    transcript_path: str | None = None
    cwd: str | None = None
    hook_event_name: str | None = None


class TaskCreatedEnvelope(NativeHookEnvelope):
    task_id: str | None = None
    task_subject: str | None = None
    task_description: str | None = None
    teammate_name: str | None = None
    team_name: str | None = None


class TaskCompletedEnvelope(TaskCreatedEnvelope):
    """TaskCompleted carrega os mesmos campos do TaskCreated (doc oficial)."""


class SubagentStopEnvelope(NativeHookEnvelope):
    stop_hook_active: bool = False
    agent_id: str | None = None
    agent_type: str | None = None
    agent_transcript_path: str | None = None
    last_assistant_message: str | None = None


class StopEnvelope(NativeHookEnvelope):
    stop_hook_active: bool = False
    last_assistant_message: str | None = None


class PreToolUseEnvelope(NativeHookEnvelope):
    tool_name: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Session registry (D1): .research/session-registry.json
# --------------------------------------------------------------------------- #
class SessionEntry(BaseModel):
    """Binding de uma sessão do Claude Code para um run kdr (D1)."""

    run_id: str
    run_dir: str
    bound_at: int = 0
    binding: str = "explicit"
    tasks: dict[str, str] = Field(default_factory=dict)
    agents: dict[str, str] = Field(default_factory=dict)


class SessionRegistry:
    """Registry persistente ``session_id -> run`` com escrita atômica.

    Load tolerante (D3): arquivo ausente ou corrompido => registry vazio,
    nunca exceção. Save atômico: tmp + ``os.replace`` no mesmo diretório
    (mesmo padrão de ``state.py``).
    """

    VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._sessions: dict[str, SessionEntry] = {}
        self.load()

    @classmethod
    def for_cwd(cls, cwd: str | Path) -> "SessionRegistry":
        """Registry do state root padrão de um cwd (``.research/runs``)."""
        return cls.for_runs_root(Path(cwd) / ".research" / "runs")

    @classmethod
    def for_runs_root(cls, runs_root: str | Path) -> "SessionRegistry":
        """Registry irmão de ``runs/`` (``<runs_root>/../session-registry.json``)."""
        return cls(Path(runs_root).parent / "session-registry.json")

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("sessions"), dict):
                self._sessions = {}
                return
            self._sessions = {
                sid: SessionEntry.model_validate(entry)
                for sid, entry in raw["sessions"].items()
            }
        except (OSError, ValueError):
            self._sessions = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "sessions": {
                sid: entry.model_dump(mode="json")
                for sid, entry in sorted(self._sessions.items())
            },
        }
        tmp = self.path.with_name(f".{self.path.name}.tmp-{os.getpid()}")
        try:
            tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, self.path)  # atômico dentro do mesmo diretório
        finally:
            tmp.unlink(missing_ok=True)

    def get(self, session_id: str | None) -> SessionEntry | None:
        if not session_id:
            return None
        return self._sessions.get(session_id)

    def bind(
        self, session_id: str, *, run_id: str, run_dir: str, binding: str
    ) -> SessionEntry:
        """Upsert do binding, preservando os mapas tasks/agents já gravados."""
        entry = self._sessions.get(session_id)
        if entry is None:
            entry = SessionEntry(run_id=run_id, run_dir=run_dir, binding=binding)
            self._sessions[session_id] = entry
        else:
            entry.run_id = run_id
            entry.run_dir = run_dir
            entry.binding = binding
        entry.bound_at = int(time.time())
        self.save()
        return entry

    def map_task(self, session_id: str, native_task_id: str, kdr_task_id: str) -> None:
        """Grava o mapeamento lazy native task_id -> kdr task_id (D2)."""
        entry = self._sessions.get(session_id)
        if entry is None:
            return
        entry.tasks[native_task_id] = kdr_task_id
        self.save()


def _active_runs(runs_root: str | Path) -> list[tuple[str, Path]]:
    """Runs com manifest ``pending``/``running`` sob ``runs_root`` (D2.2).

    Tolera manifest ausente/corrompido — o run simplesmente não conta como ativo.
    """
    runs_root = Path(runs_root)
    active: list[tuple[str, Path]] = []
    if not runs_root.is_dir():
        return active
    for child in sorted(runs_root.iterdir()):
        manifest_path = child / "manifest.json"
        if not child.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = RunManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            continue
        if manifest.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            active.append((manifest.run_id, child))
    return active


def _degraded(
    gate_id: str,
    kind: GateKind,
    check_id: str,
    description: str,
    *,
    passed: bool,
    details: object = None,
    run_id: str | None = None,
) -> GateDecision:
    """Decisão degradada (D3): um único check explicativo, nunca exceção."""
    return GateDecision.compose(
        gate_id,
        kind,
        [
            GateCheck(
                check_id=check_id,
                description=description,
                passed=passed,
                details=details,
            )
        ],
        run_id=run_id,
    )


# --------------------------------------------------------------------------- #
# Resolução de sessão (D2)
# --------------------------------------------------------------------------- #
@dataclass
class Resolution:
    """Resultado da resolução ``session_id -> run`` para um payload nativo."""

    session_id: str | None
    entry: SessionEntry | None
    runs_root: Path
    registry: SessionRegistry


def resolve_session(data: dict[str, Any]) -> Resolution:
    """Resolve a sessão do payload: binding explícito ou lazy (D2).

    ``cwd`` vem do payload (fallback: cwd do processo). Sem binding e com
    exatamente um run ativo => bind lazy (``inferred-single-run``); zero ou
    >=2 runs ativos => sem binding (ambiguidade nunca se resolve por chute).
    """
    cwd = data.get("cwd") or os.getcwd()
    runs_root = Path(cwd) / ".research" / "runs"
    registry = SessionRegistry.for_runs_root(runs_root)
    session_id = data.get("session_id")
    entry = registry.get(session_id)
    if session_id and entry is None:
        active = _active_runs(runs_root)
        if len(active) == 1:
            run_id, run_dir = active[0]
            entry = registry.bind(
                session_id,
                run_id=run_id,
                run_dir=str(run_dir.resolve()),
                binding="inferred-single-run",
            )
    return Resolution(
        session_id=session_id, entry=entry, runs_root=runs_root, registry=registry
    )


# --------------------------------------------------------------------------- #
# Insumos do run: plan, match de task e result artifact (D5)
# --------------------------------------------------------------------------- #
def _load_plan(run_dir: str | Path) -> ResearchPlan | None:
    try:
        return ResearchPlan.model_validate_json(
            (Path(run_dir) / "plan.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _match_task(
    tasks: list[TaskSpec], native_task_id: str | None, subject: str | None
) -> TaskSpec | None:
    """Match exato por ``task_id``; senão ``subject == mission`` normalizado.

    Só retorna com match único — ambiguidade nunca casa por chute (D2).
    """
    if native_task_id:
        exact = [t for t in tasks if t.task_id == native_task_id]
        if len(exact) == 1:
            return exact[0]
    if subject:
        want = _normalize(subject)
        by_mission = [t for t in tasks if _normalize(t.mission) == want]
        if len(by_mission) == 1:
            return by_mission[0]
    return None


def _read_result(path: Path) -> AgentResult | None:
    try:
        return AgentResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _load_result_artifact(
    run_dir: str | Path, kdr_task_id: str | None, plan: ResearchPlan | None
) -> AgentResult | None:
    """Lê ``agents/<task_id>/result.json``; fallback: glob com candidato único.

    O fallback só aceita exatamente um ``agents/*/result.json`` cujo
    ``task_id`` consta no plan (D5) — parsing de ``agent_transcript_path``
    fica fora de escopo (frágil; follow-up).
    """
    agents_dir = Path(run_dir) / "agents"
    if kdr_task_id:
        result = _read_result(agents_dir / kdr_task_id / "result.json")
        if result is not None:
            return result
    known_ids = {t.task_id for t in plan.tasks} if plan else set()
    candidates: list[AgentResult] = []
    for path in sorted(agents_dir.glob("*/result.json")):
        result = _read_result(path)
        if result is not None and result.task_id in known_ids:
            candidates.append(result)
    return candidates[0] if len(candidates) == 1 else None


# --------------------------------------------------------------------------- #
# Adapters (D3/D5): preparam insumos e chamam kdrx.hooks (assinaturas estáveis)
# --------------------------------------------------------------------------- #
def native_task_created(data: dict[str, Any]) -> GateDecision:
    """TaskCreated nativo: match lazy da task + gate de criação."""
    env = TaskCreatedEnvelope.model_validate(data)
    res = resolve_session(data)
    if res.entry is None:
        return _degraded(
            "hook:task_created:unbound",
            GateKind.PLAN,
            "KDR_SESSION_UNBOUND",
            "sessão sem binding para um run kdr; gate de task ignorado",
            passed=True,
            details=res.session_id,
        )
    plan = _load_plan(res.entry.run_dir)
    task = _match_task(plan.tasks if plan else [], env.task_id, env.task_subject)
    if task is None:
        return _degraded(
            "hook:task_created:unknown-task",
            GateKind.PLAN,
            "UNKNOWN_TASK",
            "task nativa não casa nenhum TaskSpec do plan; "
            "nem toda task do Claude é task kdr",
            passed=True,
            details={"task_id": env.task_id, "task_subject": env.task_subject},
            run_id=res.entry.run_id,
        )
    if env.task_id and res.session_id:
        res.registry.map_task(res.session_id, env.task_id, task.task_id)
    decision = hook_task_created(task)
    decision.run_id = res.entry.run_id
    return decision


def native_pre_tool_use(data: dict[str, Any]) -> GateDecision:
    """PreToolUse nativo: gate roda com ``run_root`` quando a sessão é bound."""
    env = PreToolUseEnvelope.model_validate(data)
    res = resolve_session(data)
    decision = hook_pre_tool_use(
        env.tool_name or "",
        env.tool_input,
        run_root=res.entry.run_dir if res.entry else None,
    )
    if res.entry is not None:
        decision.run_id = res.entry.run_id
    return decision


def native_subagent_stop(data: dict[str, Any]) -> GateDecision:
    """SubagentStop nativo: sem completion sem output válido (fail-closed)."""
    env = SubagentStopEnvelope.model_validate(data)
    res = resolve_session(data)
    if res.entry is None:
        return _degraded(
            "hook:subagent_stop:unbound",
            GateKind.CLAIM,
            "KDR_SESSION_UNBOUND",
            "sessão sem binding para um run kdr; gate de subagent ignorado",
            passed=True,
            details=res.session_id,
        )
    run_dir = Path(res.entry.run_dir)
    plan = _load_plan(run_dir)
    mapped = [
        kdr_id
        for kdr_id in res.entry.tasks.values()
        if plan is not None and plan.task_by_id(kdr_id) is not None
    ]
    for kdr_id in mapped or [None]:
        result = _load_result_artifact(run_dir, kdr_id, plan)
        if result is None or plan is None:
            continue
        task = plan.task_by_id(result.task_id)
        if task is None:
            continue
        decision = hook_subagent_stop(result, task)
        decision.run_id = res.entry.run_id
        return decision
    if mapped:
        return _degraded(
            "hook:subagent_stop:missing-artifact",
            GateKind.CLAIM,
            "RESULT_ARTIFACT_MISSING",
            "sem agents/<task_id>/result.json para a task kdr mapeada",
            passed=False,
            details={"tasks": mapped, "agent_id": env.agent_id},
            run_id=res.entry.run_id,
        )
    return _degraded(
        "hook:subagent_stop:unresolved-agent",
        GateKind.CLAIM,
        "RESULT_ARTIFACT_MISSING" if plan is None else "UNRESOLVED_AGENT",
        "não foi possível resolver o agent nativo para uma task kdr",
        passed=False,
        details={"agent_id": env.agent_id, "agent_type": env.agent_type},
        run_id=res.entry.run_id,
    )


def native_task_completed(data: dict[str, Any]) -> GateDecision:
    """TaskCompleted nativo: acceptance gate sobre o result artifact."""
    env = TaskCompletedEnvelope.model_validate(data)
    res = resolve_session(data)
    if res.entry is None:
        return _degraded(
            "hook:task_completed:unbound",
            GateKind.PLAN,
            "KDR_SESSION_UNBOUND",
            "sessão sem binding para um run kdr; acceptance gate ignorado",
            passed=True,
            details=res.session_id,
        )
    run_dir = Path(res.entry.run_dir)
    plan = _load_plan(run_dir)
    kdr_id = res.entry.tasks.get(env.task_id or "")
    task = plan.task_by_id(kdr_id) if plan and kdr_id else None
    if task is None:  # match on-the-fly: a task pode não ter passado pelo TaskCreated
        task = _match_task(plan.tasks if plan else [], env.task_id, env.task_subject)
    if task is None:
        return _degraded(
            "hook:task_completed:unknown-task",
            GateKind.PLAN,
            "UNKNOWN_TASK",
            "task nativa não casa nenhum TaskSpec do plan; acceptance não se aplica",
            passed=True,
            details={"task_id": env.task_id, "task_subject": env.task_subject},
            run_id=res.entry.run_id,
        )
    result = _load_result_artifact(run_dir, task.task_id, plan)
    if result is None:
        return _degraded(
            "hook:task_completed:missing-artifact",
            GateKind.PLAN,
            "RESULT_ARTIFACT_MISSING",
            "sem agents/<task_id>/result.json; acceptance não pode rodar",
            passed=False,
            details={"task_id": task.task_id},
            run_id=res.entry.run_id,
        )
    decision = hook_task_completed(task, result)
    decision.run_id = res.entry.run_id
    return decision


# --------------------------------------------------------------------------- #
# Stop (D4): registry + delivery-manifest persistido + validação de selo
# --------------------------------------------------------------------------- #
def _load_gate_passed(path: Path) -> bool:
    """True sse um gate persistido (``{...,"verdict": "pass"}``)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    return data.get("verdict") == "pass"


def _unresolved_critical(run_dir: Path) -> list[str]:
    """claim_ids com ``importance == CRITICAL`` e ``standing == UNRESOLVED``."""
    path = run_dir / "claims" / "claims.jsonl"
    if not path.is_file():
        return []
    out: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            claim = Claim.model_validate_json(line)
        except ValueError:
            continue
        if (
            claim.importance == ClaimImportance.CRITICAL
            and claim.standing == Standing.UNRESOLVED
        ):
            out.append(claim.claim_id)
    return out


def native_stop(data: dict[str, Any]) -> GateDecision:
    """Stop nativo (D4): gate de entrega via registry + manifest persistido + selo.

    Sem fallback por mtime: o run vem SOMENTE do registry (binding explícito
    ou lazy pela regra do run ativo único). Unbound com >=2 runs ativos =>
    block ``AMBIGUOUS_RUNS`` (fail-closed); sem ``session_id`` com runs ativos
    => block ``SESSION_ID_MISSING``; com 0 runs => allow ``ACTIVE_RUN``.
    """
    StopEnvelope.model_validate(data)  # envelope inválido => ValidationError => exit 2
    res = resolve_session(data)
    entry = res.entry
    if entry is None:
        active = _active_runs(res.runs_root)
        if not active:
            return _degraded(
                "hook:stop:no-active-run",
                GateKind.DELIVERY,
                "ACTIVE_RUN",
                "nenhum run kdr ativo sob o runs root; nada a gatear",
                passed=True,
                details=str(res.runs_root),
            )
        if not res.session_id:
            return _degraded(
                "hook:stop:session-id-missing",
                GateKind.DELIVERY,
                "SESSION_ID_MISSING",
                "payload sem session_id: impossível bindar a sessão a um run "
                "kdr; faça bind explícito (kdr plan --session-id)",
                passed=False,
                details=[run_id for run_id, _ in active],
            )
        return _degraded(
            "hook:stop:ambiguous-runs",
            GateKind.DELIVERY,
            "AMBIGUOUS_RUNS",
            "múltiplos runs ativos; faça bind explícito (kdr plan --session-id) "
            "ou conclua/arquive os runs antigos",
            passed=False,
            details=[run_id for run_id, _ in active],
        )
    run_dir = Path(entry.run_dir)
    plan = _load_plan(run_dir)
    if plan is None:
        return _degraded(
            "hook:stop:missing-plan",
            GateKind.DELIVERY,
            "PLAN_MISSING",
            "plan.json ausente ou ilegível no run bound",
            passed=False,
            details=str(run_dir),
            run_id=entry.run_id,
        )
    dag = compile_dag(plan.tasks)

    try:
        delivery = DeliveryManifest.model_validate_json(
            (run_dir / "delivery-manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        # ausente => manifest vazio => check DELIVERY_MANIFEST falha naturalmente
        delivery = DeliveryManifest(
            manifest_id=f"dm-{entry.run_id}", run_id=entry.run_id
        )

    # Validação de selo (D4.3): qualquer path alterado/ausente quebra a integridade.
    state = RunState(run_dir.parent, run_dir.name)
    try:
        manifest = state.load_manifest()
        seal_bad = state.verify_hashes(manifest.artifact_hashes)
    except (OSError, ValueError):
        seal_bad = ["manifest.json (missing)"]
    integrity_ok = not seal_bad and _load_gate_passed(
        run_dir / "verification" / "integrity.json"
    )
    security_ok = _load_gate_passed(run_dir / "verification" / "security.json")

    report_path = run_dir / "delivery" / "report.md"
    open_ok = False
    if report_path.is_file():
        try:
            report_path.read_bytes()
            open_ok = True
        except OSError:
            open_ok = False

    decision = hook_stop(
        dag=dag,
        delivery=delivery,
        integrity_pass=integrity_ok,
        secret_scan_clean=security_ok,
        artifact_open_test=open_ok,
        unresolved_critical=_unresolved_critical(run_dir),
    )
    decision.run_id = entry.run_id
    return decision


# --------------------------------------------------------------------------- #
# dispatch (D5): normaliza o nome do evento e roteia para o adapter
# --------------------------------------------------------------------------- #
_ADAPTERS: dict[str, Callable[[dict[str, Any]], GateDecision]] = {
    "task_created": native_task_created,
    "pre_tool_use": native_pre_tool_use,
    "subagent_stop": native_subagent_stop,
    "task_completed": native_task_completed,
    "stop": native_stop,
}


def _normalize_name(hook_name: str) -> str:
    return hook_name.replace("_", "").replace("-", "").lower()


_ALIASES = {_normalize_name(key): key for key in _ADAPTERS}


def dispatch(hook_name: str, data: dict[str, Any]) -> GateDecision:
    """Roteia um payload nativo para o adapter do evento.

    Aceita os nomes oficiais (``TaskCreated``, ``SubagentStop``...) e os
    snake_case do CLI legado; sem ``hook_name``, cai no ``hook_event_name``
    do payload. Nome desconhecido => ``ValueError`` (o dispatcher converte
    em exit 2).
    """
    name = hook_name or str(data.get("hook_event_name") or "")
    key = _ALIASES.get(_normalize_name(name))
    if key is None:
        raise ValueError(f"unknown native hook {hook_name}")
    return _ADAPTERS[key](data)
