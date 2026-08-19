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
    "kdr-plan": ["requirements", "scope", "retrieval", "methodology", "risk"],
    "kdr-run": ["pipeline(", "gate"],
    "kdr-verify": ["source-verifier", "devils-advocate", "final-integrity-auditor"],
    "kdr-deep-research": ["council", "synthesize", "waves", "verify", "report"],
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
