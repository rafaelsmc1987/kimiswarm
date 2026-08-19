"""Security guards and deterministic hooks."""

from __future__ import annotations

import pytest

from kdrx.dag import compile_dag
from kdrx.hooks import (
    hook_pre_tool_use,
    hook_stop,
    hook_subagent_stop,
    hook_task_created,
)
from kdrx.schemas.artifact import DeliveryManifest
from kdrx.schemas.enums import AgentRole, TaskStage
from kdrx.schemas.plan import (
    AcceptanceCriteria,
    AgentResult,
    Budget,
    RetryPolicy,
    TaskSpec,
)
from kdrx.security import (
    egress_allowed,
    is_within,
    path_traversal_attempt,
    safe_join,
    scan_secrets,
    scan_secrets_in_file,
    security_gate,
)


def test_scan_secrets_detects_keys():
    findings = scan_secrets(
        "sk-kimi-abcdefghijklmnopqrstuvwxyz123456 + AKIAABCDEFGHIJKLMNOP"
    )
    kinds = {f.kind for f in findings}
    assert "kimi_sk" in kinds
    assert "aws_access_key" in kinds


def test_scan_secrets_in_file(tmp_path):
    p = tmp_path / "s.txt"
    p.write_text("api_key=1234567890123456\nhello\n")
    findings = scan_secrets_in_file(p)
    assert any(f.kind == "named_secret" for f in findings)


def test_is_within_and_safe_join(tmp_path):
    assert is_within(tmp_path, tmp_path / "a" / "b")
    assert not is_within(tmp_path / "a", tmp_path / "b")
    with pytest.raises(ValueError):
        safe_join(tmp_path, "../escape")


def test_path_traversal_attempt():
    assert path_traversal_attempt("../x")
    assert path_traversal_attempt("/abs")
    assert not path_traversal_attempt("a/b")


def test_egress_allowed():
    assert not egress_allowed("evil.com", allowlist=["good.com"])
    assert egress_allowed("sub.good.com", allowlist=["good.com"])
    assert not egress_allowed("good.com", allowlist=["good.com"], denylist=["good.com"])


def test_security_gate_flags_secret(tmp_path):
    (tmp_path / "clean.txt").write_text("fine")
    assert security_gate(tmp_path).verdict.value == "pass"
    (tmp_path / "dirty.txt").write_text("password=supersecretvalue123")
    assert security_gate(tmp_path).blocking()


def _task(**kw):
    defaults = dict(
        task_id="T",
        stage=TaskStage.RETRIEVAL,
        wave=0,
        role=AgentRole.WEB_EXPLORER,
        mission="m",
        outputs=["o"],
        acceptance=AcceptanceCriteria(criteria=["c"]),
        retry_policy=RetryPolicy(),
        budget=Budget(tokens=1),
        owner="me",
    )
    defaults.update(kw)
    return TaskSpec(**defaults)


def test_hook_task_created_requires_owner():
    assert hook_task_created(_task(owner="")).blocking()


def test_hook_pre_tool_use_blocks_traversal():
    d = hook_pre_tool_use("Write", {"file_path": "../escape.txt"}, run_root="/run")
    assert d.blocking()


def test_hook_pre_tool_use_blocks_unauthorized():
    d = hook_pre_tool_use("Write", {"file_path": "ok.txt"}, authorized_tools=["Read"])
    assert d.blocking()


def test_hook_subagent_stop_requires_outputs():
    r = AgentResult(
        result_id="r",
        task_id="T",
        agent_role=AgentRole.WEB_EXPLORER,
        outputs_produced=[],
    )
    assert hook_subagent_stop(r, _task()).blocking()


def test_hook_stop_requires_clean_delivery():
    dag = compile_dag([_task()])
    empty = DeliveryManifest(manifest_id="d", run_id="r")
    d = hook_stop(
        dag=dag,
        delivery=empty,
        integrity_pass=False,
        secret_scan_clean=False,
        artifact_open_test=False,
        unresolved_critical=["C1"],
    )
    assert d.blocking()
