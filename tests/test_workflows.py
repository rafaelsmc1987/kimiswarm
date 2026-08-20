"""T-02-01..T-02-04: workflows dinâmicos do plugin (structural validation).

O runtime de workflows é o Claude Code (>= v2.1.154): `export const meta`,
`agent()`/`pipeline()`/`parallel()`/`phase()` globais, `args` de entrada,
`return` de topo e top-level await — NENHUM runtime genérico executa isso
direto (ESM rejeita return de topo, CJS rejeita await de topo). A validação
determinística aqui compila o corpo como AsyncFunction (que aceita await e
return de topo, exatamente o modelo do runtime) e o meta como object literal,
além das checagens estruturais exigidas pelo runtime e pelos gates KDR-X.

Demos E2E com fan-out real ficam para CI/live: exigem runtime Claude Code.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "kdr-x"
WORKFLOWS = PLUGIN / "workflows"
EXPECTED = {
    "kdr-plan": [
        "requirements",
        "scope",
        "retrieval",
        "methodology",
        "risk",
        "import-plan",
        "--objective-file",
    ],
    "kdr-run": ["pipeline(", "gate"],
    "kdr-verify": ["source-verifier", "devils-advocate", "final-integrity-auditor"],
    "kdr-deep-research": [
        "council",
        "synthesize",
        "waves",
        "verify",
        "report",
        "seal",
        "kdr seal",
        "verified_report_hash",
        "MAX_SEAL_REPAIRS",
        "--objective-file",
    ],
}

NODE = shutil.which("node") or shutil.which("node.exe")


def _read(name: str) -> str:
    path = WORKFLOWS / f"{name}.js"
    assert path.is_file(), f"workflow ausente: {path}"
    return path.read_text(encoding="utf-8")


def test_all_workflows_present_and_guarded_input():
    for name in EXPECTED:
        text = _read(name)
        assert re.search(r"export const meta = \{", text), f"{name}: meta ausente"
        m = re.search(r"name:\s*'([^']+)'", text)
        assert m and m.group(1) == name, f"{name}: meta.name diverge"
        assert "args === undefined" in text, (
            f"{name}: deve falhar explicitamente sem args"
        )


def test_no_runtime_forbidden_constructs():
    # Constraints do runtime (code.claude.com/docs/en/workflows): sem import(),
    # sem require(), sem acesso direto a fs/shell no corpo do script.
    for name in EXPECTED:
        text = _read(name)
        assert "import(" not in text, f"{name}: import() proibido pelo runtime"
        assert not re.search(r"\brequire\(", text), f"{name}: require() proibido"
        assert "child_process" not in text


def test_null_results_handled_explicitly():
    # agent()/pipeline() podem retornar null (T-02-06): nunca silencioso.
    for name in EXPECTED:
        text = _read(name)
        assert "filter(Boolean)" in text or "=== null" in text or "||" in text, (
            f"{name}: tratar null dos agents explicitamente"
        )


def test_expected_structure_per_workflow():
    for name, markers in EXPECTED.items():
        text = _read(name)
        for marker in markers:
            assert marker in text, f"{name}: marcador ausente {marker!r}"


def test_kdr_plan_fans_out_all_five_planners_and_pipeline_run():
    plan = _read("kdr-plan")
    # 5 planners + reviewer + verifier + synthesizer (audit T-02-01 aceite)
    assert plan.count("phase:") >= 1
    assert "parallel(" in plan, "kdr-plan: fan-out real exige parallel()"
    assert plan.count("agent(") >= 4, "kdr-plan: planner/reviewer/verifier/synthesizer"
    run = _read("kdr-run")
    assert "pipeline(" in run, "kdr-run: waves exigem pipeline() (concorrência real)"
    assert "phase('gate')" in run, "kdr-run: gate entre waves"


def test_python_boundary_respected():
    # T-02-08: workflows orquestram agents; Python (kdr CLI) fica com
    # schemas/state/gates — os workflows NÃO reimplementam gates em JS, só os
    # invocam/verificam artefatos.
    for name in ("kdr-run", "kdr-verify", "kdr-deep-research"):
        text = _read(name)
        assert "kdr " in text or "kdrx" in text, (
            f"{name}: deve usar a CLI kdr para gates"
        )


def test_plugin_manifest_declares_workflows():
    manifest = json.loads(
        (PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    rel = manifest.get("workflows", "./workflows")
    assert (PLUGIN / rel).is_dir(), "manifest declare workflows e o dir deve existir"


# --------------------------------------------------------------------------- #
# Compilação estrutural: AsyncFunction emula o dialeto do runtime
# (await + return de topo; globals injetados). Parse error = SyntaxError.
# --------------------------------------------------------------------------- #
NODE_CHECK_SCRIPT = r"""
const fs = require('fs');
const path = process.argv[1];
const text = fs.readFileSync(path, 'utf8');
const m = text.match(/export const meta = (\{[\s\S]*?\n\})/);
if (!m) { console.error('NO_META'); process.exit(3); }
let meta;
try { meta = (new Function('return (' + m[1] + ')'))(); }
catch (e) { console.error('META_SYNTAX: ' + e.message); process.exit(4); }
const body = text.replace(m[0], '');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
try { new AsyncFunction('agent', 'pipeline', 'parallel', 'phase', 'args', body); }
catch (e) { console.error('BODY_SYNTAX: ' + e.message); process.exit(5); }
if (typeof meta.name !== 'string' || typeof meta.description !== 'string') {
  console.error('META_FIELDS'); process.exit(6);
}
console.log('OK ' + meta.name);
"""


@pytest.mark.skipif(NODE is None, reason="node indisponível neste host")
def test_workflow_bodies_compile_as_runtime_dialect():
    for path in sorted(WORKFLOWS.glob("kdr-*.js")):
        proc = subprocess.run(
            [NODE, "-e", NODE_CHECK_SCRIPT, str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert proc.returncode == 0, f"{path.name}: {proc.stdout}{proc.stderr}"
        assert proc.stdout.startswith("OK kdr-"), proc.stdout


# --------------------------------------------------------------------------- #
# SW-02: gate canônico de import + schema flattened com paridade pydantic.
# --------------------------------------------------------------------------- #

REQUIRED_TASK_KEYS = {
    "task_id",
    "stage",
    "wave",
    "role",
    "mission",
    "dependencies",
    "inputs",
    "outputs",
    "skills",
    "tools",
    "read_only",
    "source_policy",
    "acceptance",
    "retry_policy",
    "budget",
    "criticality",
    "status",
    "owner",
    "reviewer",
    "guidance",
    "metadata",
}

# Extrai o object literal do PLAN_SCHEMA (entre os marcadores das consts) e o
# avalia como object literal — mesmo truque do NODE_CHECK_SCRIPT, mas para o
# schema do synthesizer. NODE só é usado para extrair; a comparação com o
# runtime pydantic é feita no Python.
PLAN_SCHEMA_NODE_SCRIPT = r"""
const fs = require('fs');
const path = process.argv[1];
const text = fs.readFileSync(path, 'utf8');
const start = text.indexOf('const PLAN_SCHEMA = ');
const end = text.indexOf('\nconst SYNTHESIS_SCHEMA', start);
if (start < 0 || end < 0) { console.error('NO_SCHEMAS'); process.exit(3); }
let lit = text.slice(start + 'const PLAN_SCHEMA = '.length, end).trim();
// corta comentários à direita (o fecho do literal é o único '\n}' em coluna 0;
// comentário final engoliria o ')' de fechamento do wrapper)
const close = lit.lastIndexOf('\n}');
if (close >= 0) lit = lit.slice(0, close + 2);
let plan;
try { plan = (new Function('return (' + lit + ')'))(); }
catch (e) { console.error('SCHEMA_SYNTAX: ' + e.message); process.exit(4); }
const task = plan.properties.tasks.items;
console.log(JSON.stringify({
  planRequired: plan.required,
  taskRequired: task.required,
  taskKeys: Object.keys(task.properties),
  roleEnum: task.properties.role.enum,
  stageEnum: task.properties.stage.enum,
  statusEnum: task.properties.status.enum,
  criticalityEnum: task.properties.criticality.enum,
}));
"""


def _runtime_enum_members():
    """Membros (TaskStage, AgentRole) do runtime pydantic, se importável."""
    try:
        from kdrx.schemas.enums import AgentRole, TaskStage
    except ImportError:
        return None, None
    return [m.value for m in TaskStage], [m.value for m in AgentRole]


def test_kdr_plan_review_gate_repair_bound_and_import():
    plan = _read("kdr-plan")
    assert re.search(r"const MAX_REPAIRS = 2\b", plan), "MAX_REPAIRS deve ser 2 (D3)"
    assert "council:repair:" in plan, "repair loop com label council:repair:N"
    assert "!review.approved" in plan, "review.approved deve gatear o fluxo"
    assert "dispositions" in plan, "SYNTHESIS_SCHEMA deve carregar dispositions (D5)"
    assert "SYNTHESIS_SCHEMA" in plan
    assert "IMPORT_SCHEMA" in plan
    assert "plan_hash" in plan
    assert "phase('scaffold')" in plan
    assert "phase('import')" in plan
    assert "run_dir: scaffold.run_dir" in plan, "D9: retorno usa run_dir"


def test_kdr_deep_research_verify_report_seal_order():
    # SW-03 D3/F4: verify (adversarial, pré-report) -> report (assemble) ->
    # seal (verify-then-seal determinístico sobre os BYTES finais).
    text = _read("kdr-deep-research")
    m = re.search(r"phases:\s*\[([^\]]+)\]", text)
    assert m, "meta.phases ausente"
    phases = [p.strip().strip("'") for p in m.group(1).split(",")]
    assert phases[-1] == "seal", f"phases devem terminar em seal: {phases}"
    assert phases.index("verify") < phases.index("report") < phases.index("seal"), (
        f"ordem errada: {phases}"
    )
    # Verify usa o STDOUT do kdr verify (fixa o false-negative do caminho JS:
    # verification/*.json não existem antes do seal).
    assert "verify: PASS" in text, "verify deve parsear a linha verify: PASS do stdout"
    assert "verification/integrity.json" not in text, (
        "verify não pode mais ler verification/*.json (inexistentes no caminho JS)"
    )


def test_kdr_deep_research_seal_schema_and_repair_bound():
    text = _read("kdr-deep-research")
    # SEAL_SCHEMA: parse do stdout JSON de `kdr seal --json`
    assert "SEAL_SCHEMA" in text
    assert "'verdict'" in text and "'sealed'" in text
    assert "kdr seal --run-dir" in text
    # N=1 fixo: loop de repair bounded por MAX_SEAL_REPAIRS
    assert re.search(r"MAX_SEAL_REPAIRS\s*=\s*1\b", text), "MAX_SEAL_REPAIRS deve ser 1"
    assert "sealRepairs < MAX_SEAL_REPAIRS" in text
    assert "dr:seal:repair:" in text, "repair com label dr:seal:repair:N"
    # Segundo fail => blocking (derivado do selo)
    assert "blocking = verdict !== 'pass' || !sealed" in text


def test_kdr_deep_research_return_carries_seal_state():
    text = _read("kdr-deep-research")
    ret = text[text.rfind("return {") :]
    assert "sealed" in ret, "return deve carregar sealed"
    assert "verified_report_hash" in ret, "return deve carregar verified_report_hash"
    assert "delivered_at" in ret, "return deve carregar delivered_at"
    assert "kdr seal" in ret, "next deve apontar para kdr seal manual (idempotente)"


def test_no_objective_shell_interpolation():
    # D6: o objective nunca é interpolado no shell (nem via replace lossy).
    for name in EXPECTED:
        text = _read(name)
        assert '.replace(/"/g' not in text, (
            f"{name}: interpolação lossy do objective proibida (D6)"
        )
        assert '--objective "' not in text, (
            f"{name}: objective inline no shell proibido (D6)"
        )


@pytest.mark.skipif(NODE is None, reason="node indisponível neste host")
def test_plan_schema_parity_with_pydantic():
    proc = subprocess.run(
        [NODE, "-e", PLAN_SCHEMA_NODE_SCRIPT, str(WORKFLOWS / "kdr-plan.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert proc.returncode == 0, f"extração do PLAN_SCHEMA: {proc.stdout}{proc.stderr}"
    data = json.loads(proc.stdout)

    # D2: o TaskSpec do JS deve expor TODOS os campos do TaskSpec pydantic.
    assert REQUIRED_TASK_KEYS <= set(data["taskKeys"]), (
        f"TaskSpec do JS perdeu campos: {REQUIRED_TASK_KEYS - set(data['taskKeys'])}"
    )
    assert set(data["taskRequired"]) == {
        "task_id",
        "stage",
        "wave",
        "role",
        "mission",
        "dependencies",
        "outputs",
    }
    assert set(data["planRequired"]) == {
        "plan_id",
        "contract_id",
        "route",
        "plan_md",
        "tasks",
    }

    # Enums de contrato canônico (tamanhos fixos, sem duplicatas).
    assert set(data["stageEnum"]) == {
        "intake",
        "planning",
        "retrieval",
        "verification",
        "analysis",
        "synthesis",
        "writing",
        "review",
        "delivery",
    }
    assert set(data["criticalityEnum"]) == {"high", "medium", "low"}
    assert len(data["statusEnum"]) == 9
    assert len(data["roleEnum"]) == len(set(data["roleEnum"])), (
        "role enum com duplicatas"
    )

    stage_members, role_members = _runtime_enum_members()
    if stage_members is None or role_members is None:
        # kdrx não importável neste host: bound conservador (AgentRole >= 50).
        assert len(data["roleEnum"]) >= 50, "role enum suspeitamente curto"
    else:
        assert set(data["roleEnum"]) == set(role_members), (
            "role enum do JS diverge do AgentRole runtime"
        )
        assert set(data["stageEnum"]) == set(stage_members)
