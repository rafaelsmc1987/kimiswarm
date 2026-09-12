import json
import sys
import time

import pytest

from kdrx.application.live import add_live_tasks
from kdrx.integrations.model_cli import (
    ModelConfig,
    ModelError,
    ModelReply,
    command,
    parse_events,
    run_process,
)
from kdrx.retrieval import FileCorpus
from kdrx.runner import build_contract, build_plan, execute_plan, prepare_run_dir


def payload(text="A bounded response"):
    return {"text": text, "evidence_refs": [], "limitations": [], "blocking_issues": []}


@pytest.mark.parametrize("provider", ["codex", "claude-code"])
def test_exact_stdin_and_structured_process(provider, tmp_path):
    prompt = 'Ação; "quotes" $(whoami) & < > |\nSecond line'
    if provider == "codex":
        script = "import sys,json; text=sys.stdin.buffer.read().decode('utf-8'); print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':json.dumps({'text':text,'evidence_refs':[],'limitations':[],'blocking_issues':[]})}})); print(json.dumps({'type':'turn.completed','usage':{'input_tokens':12,'output_tokens':4}}))"
    else:
        script = "import sys,json; text=sys.stdin.buffer.read().decode('utf-8'); print(json.dumps({'type':'result','subtype':'success','structured_output':{'text':text,'evidence_refs':[],'limitations':[],'blocking_issues':[]},'usage':{'input_tokens':12,'output_tokens':4}}))"
    raw, _, code = run_process(
        [sys.executable, "-c", script],
        prompt.encode(),
        tmp_path,
        ModelConfig(provider=provider),
    )
    reply, receipt = parse_events(provider, raw)
    assert code == 0 and reply.text == prompt
    assert receipt["usage"]["input_tokens"] == 12
    assert receipt["cost_usd"] is None


def test_actual_subprocess_timeout_and_output_bounds(tmp_path):
    started = time.monotonic()
    with pytest.raises(ModelError, match="timeout"):
        run_process(
            [sys.executable, "-c", "import time; time.sleep(20)"],
            b"",
            tmp_path,
            ModelConfig(timeout_seconds=0.15),
        )
    assert time.monotonic() - started < 5
    with pytest.raises(ModelError, match="output_limit"):
        run_process(
            [sys.executable, "-c", "print('x'*100000)"],
            b"",
            tmp_path,
            ModelConfig(max_output_bytes=1024),
        )


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not JSON",
        b'{"type":"turn.completed"}',
        b'{"type":"error"}',
        b'{"type":"item.completed","item":{"type":"command_execution"}}',
    ],
)
def test_partial_or_tool_output_never_succeeds(raw):
    with pytest.raises(ModelError):
        parse_events("codex", raw)


def test_inference_configuration_disables_host_tools(tmp_path):
    codex = command(ModelConfig(provider="codex"), tmp_path, binary="codex")
    assert "--ignore-user-config" in codex and "--strict-config" in codex
    assert (
        "features.shell_tool=false" in codex and "features.multi_agent=false" in codex
    )
    claude = command(ModelConfig(provider="claude-code"), tmp_path, binary="claude")
    assert claude[claude.index("--tools") + 1] == ""
    assert "--safe-mode" in claude
    assert not any("dangerously" in arg for arg in codex + claude)


def test_five_specialists_use_committed_evidence_and_cannot_authorize_delivery(
    tmp_path, monkeypatch
):
    import kdrx.integrations.model_cli as cli

    monkeypatch.setattr(
        cli, "provider_status", lambda _: {"authenticated": True, "subscription": True}
    )
    roles = []

    def infer(self, prompt, attempt_id, cancelled=None):
        context = json.loads(prompt.split("\n", 1)[1])
        roles.append(context["role"])
        assert context["spans"] and context["claims"]
        reply = payload(
            context["draft"]
            if context["role"] == "section_writer"
            else "Review complete"
        )
        return ModelReply.model_validate(reply), {
            "provider": "simulated",
            "attempt_id": attempt_id,
        }

    monkeypatch.setattr(cli.CLIModelBackend, "infer", infer)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "study.txt").write_text("Latency is 5 ms under load.", encoding="utf-8")
    contract = build_contract("latency under load")
    plan = add_live_tasks(build_plan(contract), "codex")
    state, _ = prepare_run_dir(plan, contract, tmp_path / "runs")
    result, _ = execute_plan(
        plan, contract, FileCorpus(corpus), state, model_config=ModelConfig(max_calls=5)
    )
    assert not result.failed
    assert len(roles) == len(set(roles)) == 5
    assert state._resolve("delivery/report.md").is_file()
    assert state._resolve("verification/model_review.json").is_file()


def test_zero_budget_rejected_before_auth_or_model_call(tmp_path, monkeypatch):
    import kdrx.integrations.model_cli as cli

    monkeypatch.setattr(
        cli,
        "provider_status",
        lambda _: pytest.fail("should not check auth with zero budget"),
    )
    with pytest.raises(ModelError, match="max_calls is zero"):
        cli.CLIModelBackend(ModelConfig(), None, "run")
