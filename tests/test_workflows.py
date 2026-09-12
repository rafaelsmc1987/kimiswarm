"""Kernel facade contracts under an emulated host. These are not live host tests."""

import base64
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from kdrx.schemas import SCHEMAS

PLUGIN = Path(__file__).resolve().parents[1] / "plugins/kdr-x"
WORKFLOWS = PLUGIN / "workflows"
OPERATIONS = {
    "kdr-plan": "plan",
    "kdr-run": "run",
    "kdr-verify": "verify",
    "kdr-deep-research": "research",
}
NODE = shutil.which("node")

NODE_HARNESS = r"""
const fs = require('fs');
const text = fs.readFileSync(process.argv[1], 'utf8');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const match = text.match(/export const meta = (\{[\s\S]*?\n\})/);
if (!match) throw Error('Missing metadata');
const meta = new Function('return (' + match[1] + ')')();
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const body = new AsyncFunction('agent', 'phase', 'args', text.replace(match[0], ''));
const calls = [];
body(async (prompt, options) => { calls.push({prompt, options}); return data.agent_result; },
     () => {}, data.args).then(result => console.log(JSON.stringify({meta, result, calls})))
     .catch(error => {console.error(error); process.exitCode=1;});
"""


def run_facade(name, args, agent_result):
    if NODE is None:
        pytest.skip("Node is unavailable; host emulation not executed")
    process = subprocess.run(
        [NODE, "-e", NODE_HARNESS, str(WORKFLOWS / f"{name}.js")],
        input=json.dumps({"args": args, "agent_result": agent_result}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


@pytest.mark.parametrize("name", OPERATIONS)
def test_workflow_rejects_missing_input(name):
    output = run_facade(name, None, None)
    assert output["result"]["blocking"] is True
    assert output["calls"] == []


@pytest.mark.parametrize("name", OPERATIONS)
def test_agent_cannot_grant_delivery_approval(name):
    forged = {
        "passed": True,
        "sealed": True,
        "deliverable": True,
        "receipt_id": "invented",
    }
    output = run_facade(
        name,
        {"objective": "Question", "corpus": "input", "run_dir": "runs/run-1"},
        forged,
    )
    assert output["result"]["authoritative"] is False
    assert output["result"]["verification_required"] is True
    assert "deliverable" not in output["result"] and "sealed" not in output["result"]
    assert len(output["calls"]) == 1


@pytest.mark.parametrize("name,operation", OPERATIONS.items())
def test_transport_is_literal_and_plan_stays_in_kernel(name, operation):
    objective = 'A??o "quoted"; $(command) & | < >'
    output = run_facade(
        name,
        {"objective": objective, "corpus": "space dir", "run_dir": "runs/run-1"},
        "observed",
    )
    command = output["calls"][0]["prompt"].split("Command: ")[1]
    assert re.fullmatch(r"kdr request --payload-base64 [A-Za-z0-9+/=]+", command)
    payload = json.loads(base64.b64decode(command.split()[-1]))
    assert payload["objective"] == objective
    assert payload["operation"] == operation
    assert "tasks" not in payload and "waves" not in payload
    assert payload["run_dir"] == "runs/run-1"


@pytest.mark.parametrize("name", OPERATIONS)
def test_null_agent_blocks_without_second_execution(name):
    output = run_facade(name, {"objective": "Question"}, None)
    assert output["result"]["blocking"] is True
    assert len(output["calls"]) == 1


def test_no_runtime_forbidden_constructs():
    for name in OPERATIONS:
        text = (WORKFLOWS / f"{name}.js").read_text(encoding="utf-8")
        assert (
            "import(" not in text
            and "require(" not in text
            and "child_process" not in text
        )
        assert ".kdr-objective.txt" not in text


def test_plugin_manifest_declares_workflows():
    manifest = json.loads(
        (PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
    )
    assert (PLUGIN / manifest["workflows"]).is_dir()


def test_exported_schemas_match_canonical_models():
    for name, model in SCHEMAS.items():
        schema = json.loads(
            (PLUGIN / f"schemas/{name}.schema.json").read_text(encoding="utf-8")
        )
        assert schema == model.model_json_schema(), name
