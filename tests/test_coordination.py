import json
import time
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from kdrx.runner import build_contract, build_plan, prepare_run_dir
from kdrx.runtime.blackboard import Blackboard
from kdrx.runtime.notifications import Notifications
from kdrx.runtime.resources import ResourceLocks
from kdrx.runtime.store import StateConflict
from kdrx.schemas.coordination import (
    CoordinationPolicy,
    HelpRequested,
    MessageScope,
    SourceDiscovered,
)


def setup_run(tmp_path, **policy):
    contract = build_contract("latency")
    plan = build_plan(contract)
    state, _ = prepare_run_dir(plan, contract, tmp_path / "runs")
    state.store.register_tasks(state.run_id, [t.task_id for t in plan.tasks])
    board = Blackboard(state)
    board.configure(CoordinationPolicy(enabled=True, **policy))
    return state, plan, board


def source(state, task="T-RETRIEVE", **updates):
    data = dict(
        run_id=state.run_id,
        plan_revision=0,
        task_id=task,
        scope=MessageScope(subquestion_id="latency"),
        refs=[{"kind": "source", "ref_id": "source-one", "sha256": "a" * 64}],
        canonical_uri="https://example.org/study",
        content_hash="a" * 64,
    )
    data.update(updates)
    return SourceDiscovered(**data)


def test_same_source_from_two_workers_creates_one_discovery_and_notification(tmp_path):
    state, plan, board = setup_run(tmp_path)
    queue = Notifications(state.store)
    queue.subscribe(
        state.run_id,
        "review",
        task_id=plan.tasks[1].task_id,
        kinds=["SourceDiscovered"],
        subquestion_id="latency",
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(board.publish, [source(state), source(state, "T-VERIFY")])
        )
    assert results[0]["event_id"] == results[1]["event_id"]
    message = queue.claim(state.run_id, "review", "worker")
    assert message and queue.claim(state.run_id, "review", "other") is None
    effects = []
    assert queue.consume(message, lambda db, event: effects.append(event["event_id"]))
    assert not queue.consume(message, lambda db, event: effects.append("duplicate"))
    assert effects == [results[0]["event_id"]]


def test_notification_expiry_fences_old_consumer_and_retries_atomically(tmp_path):
    state, _, board = setup_run(tmp_path)
    queue = Notifications(state.store)
    queue.subscribe(
        state.run_id, "review", task_id="T-VERIFY", kinds=["SourceDiscovered"]
    )
    board.publish(source(state))
    old = queue.claim(state.run_id, "review", "old", seconds=0.01)
    time.sleep(0.02)
    new = queue.claim(state.run_id, "review", "new")
    with pytest.raises(StateConflict):
        queue.consume(old, lambda db, event: None)
    with state.store.transaction() as db:
        db.execute("CREATE TABLE effects(id TEXT PRIMARY KEY)")

    def consume(db, event):
        db.execute("INSERT INTO effects VALUES(?)", (event["event_id"],))

    assert queue.consume(new, consume)
    assert not queue.consume(new, consume)
    with state.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM effects").fetchone()[0] == 1


def test_consumer_failure_rolls_back_effect_and_dead_letters_after_limit(tmp_path):
    state, _, board = setup_run(tmp_path, max_delivery_attempts=2, retry_seconds=0)
    queue = Notifications(state.store)
    queue.subscribe(
        state.run_id, "review", task_id="T-VERIFY", kinds=["SourceDiscovered"]
    )
    board.publish(source(state))
    with state.store.transaction() as db:
        db.execute("CREATE TABLE effects(id TEXT)")

    def failing(db, event):
        db.execute("INSERT INTO effects VALUES(?)", (event["event_id"],))
        raise RuntimeError("consumer failed")

    for _ in range(2):
        lease = queue.claim(state.run_id, "review", "worker")
        with pytest.raises(RuntimeError):
            queue.consume(lease, failing)
    assert queue.claim(state.run_id, "review", "worker") is None
    assert queue.status(state.run_id)["dead"] == 1
    with state.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM effects").fetchone()[0] == 0


def test_circular_help_rejected_with_diagnostic_and_no_hidden_dependency(tmp_path):
    state, plan, board = setup_run(tmp_path)

    def request(requester, helper, revision):
        return HelpRequested(
            run_id=state.run_id,
            plan_revision=revision,
            task_id=requester,
            scope=MessageScope(task_id=helper),
            refs=[{"kind": "task", "ref_id": helper}],
            reason="independent validation",
            helper_task_id=helper,
            budget={"tokens": 1, "queries": 0, "wall_seconds": 10},
            deadline=time.time() + 60,
        )

    # Existing graph has VERIFY -> RETRIEVE; the reverse request must be rejected.
    with pytest.raises(ValueError, match="cycle|CYCLE"):
        board.request_help(request("T-RETRIEVE", "T-VERIFY", 0))
    assert json.loads(state.read_text("plan.json"))["plan_revision"] == 0
    assert any(e["kind"] == "help_rejected" for e in state.store.events(state.run_id))
    accepted = board.request_help(request("T-INTEGRITY", "T-VERIFY", 0))
    assert accepted["plan_revision"] == 1
    assert (
        "T-VERIFY"
        in json.loads(state.read_text("plan.json"))["tasks"][-1]["dependencies"]
    )


def test_message_limits_and_scope_are_enforced_without_silent_overflow(tmp_path):
    state, _, board = setup_run(tmp_path, max_messages=1)
    first = source(state)
    board.publish(first)
    assert board.publish(first)["kind"] == "SourceDiscovered"
    with pytest.raises(ValueError, match="budget"):
        board.publish(source(state, canonical_uri="https://example.org/second"))
    with pytest.raises(ValueError):
        board.publish(source(state, task="unknown"))


def test_resource_acquisition_is_atomic_ordered_and_expiring(tmp_path):
    state, plan, _ = setup_run(tmp_path)
    locks = ResourceLocks(state.store)
    first = state.store.claim(state.run_id, plan.tasks[0].task_id, "one")
    second = state.store.claim(state.run_id, plan.tasks[1].task_id, "two")
    held = locks.acquire(first, ["browser", "export"], seconds=0.01)
    with pytest.raises(StateConflict, match="order"):
        locks.acquire(first, ["audio"])
    with pytest.raises(StateConflict, match="busy"):
        locks.acquire(second, ["audio", "browser"])
    with state.store.connect() as db:
        assert not db.execute(
            "SELECT 1 FROM resource_locks WHERE resource='audio'"
        ).fetchone()
    time.sleep(0.02)
    current = locks.acquire(second, ["browser", "export"])
    with pytest.raises(StateConflict):
        locks.check(first, held)
    locks.check(second, current)


def test_real_task_commit_publishes_artifact_notifications_in_same_transaction(
    tmp_path,
):
    from kdrx.runner import execute_plan
    from kdrx.retrieval import FileCorpus

    state, plan, _ = setup_run(tmp_path)
    queue = Notifications(state.store)
    queue.subscribe(
        state.run_id, "review", task_id="T-VERIFY", kinds=["ArtifactCommitted"]
    )
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "study.txt").write_text("Latency is 5 ms under load.", encoding="utf-8")
    result, _ = execute_plan(plan, build_contract("latency"), FileCorpus(corpus), state)
    assert result.deliverable
    event = queue.claim(state.run_id, "review", "consumer")
    assert event["event"]["kind"] == "ArtifactCommitted"
    for ref in event["event"]["refs"]:
        assert any(
            a["hash"] == ref["sha256"]
            for a in state.store.artifacts(state.run_id, "T-RETRIEVE")
        )


def test_messages_are_disabled_by_default_and_cannot_cross_runs(tmp_path):
    state, _, board = setup_run(tmp_path)
    message = source(state)
    board.publish(message)
    other, _ = prepare_run_dir(
        build_plan(build_contract("other")), build_contract("other"), tmp_path / "other"
    )
    with pytest.raises(StateConflict, match="run"):
        Blackboard(other).publish(message)
    with pytest.raises(StateConflict, match="disabled"):
        Blackboard(other).publish(source(other))


def test_process_kill_during_consumer_transaction_rolls_back_inbox_and_effect(tmp_path):
    state, _, board = setup_run(tmp_path)
    queue = Notifications(state.store)
    queue.subscribe(
        state.run_id, "review", task_id="T-VERIFY", kinds=["SourceDiscovered"]
    )
    board.publish(source(state))
    with state.store.transaction() as db:
        db.execute("CREATE TABLE effects(id TEXT PRIMARY KEY)")
    script = """
import os,sys
from pathlib import Path
from kdrx.runtime.store import SQLiteStore
from kdrx.runtime.notifications import Notifications
queue=Notifications(SQLiteStore(Path(sys.argv[1])))
delivery=queue.claim(sys.argv[2],'review','child',seconds=.1)
def effect(db,event):
    db.execute('INSERT INTO effects VALUES(?)',(event['event_id'],))
    os._exit(93)
queue.consume(delivery,effect)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(state.store.path), state.run_id],
        capture_output=True,
    )
    assert child.returncode == 93, child.stderr
    time.sleep(0.12)
    with state.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM effects").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM notification_inbox").fetchone()[0] == 0
    retry = queue.claim(state.run_id, "review", "replacement")
    queue.consume(
        retry,
        lambda db, event: db.execute(
            "INSERT INTO effects VALUES(?)", (event["event_id"],)
        ),
    )
    assert queue.status(state.run_id) == {"acked": 1}


def test_failed_event_transaction_does_not_leave_notification(tmp_path):
    state, _, _ = setup_run(tmp_path)
    queue = Notifications(state.store)
    queue.subscribe(
        state.run_id, "review", task_id="T-VERIFY", kinds=["task_committed"]
    )
    with pytest.raises(RuntimeError):
        with state.store.transaction() as db:
            state.store.event(db, state.run_id, {"kind": "task_committed"})
            raise RuntimeError("interrupted")
    assert queue.status(state.run_id) == {}
    assert not any(
        e["kind"] == "task_committed" for e in state.store.events(state.run_id)
    )


def test_notification_consumer_uses_persisted_payload_and_dead_letters_overflow(
    tmp_path,
):
    state, _, board = setup_run(tmp_path, max_pending=1)
    queue = Notifications(state.store)
    queue.subscribe(
        state.run_id, "review", task_id="T-VERIFY", kinds=["SourceDiscovered"]
    )
    original = board.publish(source(state))
    board.publish(source(state, canonical_uri="https://example.org/second"))
    assert queue.status(state.run_id) == {"dead": 1, "pending": 1}
    delivery = queue.claim(state.run_id, "review", "worker")
    delivery["event"] = {"forged": True}
    seen = []
    queue.consume(delivery, lambda db, event: seen.append(event))
    assert seen == [original]


def test_help_budget_failure_rolls_back_plan_patch_and_retry_is_idempotent(tmp_path):
    state, _, board = setup_run(tmp_path, max_messages=0)
    request = HelpRequested(
        run_id=state.run_id,
        plan_revision=0,
        task_id="T-INTEGRITY",
        scope=MessageScope(task_id="T-VERIFY"),
        refs=[{"kind": "task", "ref_id": "T-VERIFY"}],
        helper_task_id="T-VERIFY",
        reason="review",
        budget={"tokens": 0, "queries": 0, "wall_seconds": 1},
        deadline=time.time() + 20,
    )
    with pytest.raises(ValueError, match="budget"):
        board.request_help(request)
    assert state.load_manifest().plan_revision == 0
    with state.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM plan_revisions").fetchone()[0] == 1


def test_coordination_cli_persists_received_message_before_ack(tmp_path, capsys):
    from kdrx.cli import main

    state, _, board = setup_run(tmp_path)
    queue = Notifications(state.store)
    queue.subscribe(
        state.run_id, "review", task_id="T-VERIFY", kinds=["SourceDiscovered"]
    )
    board.publish(source(state))
    assert (
        main(
            [
                "coordination",
                "receive",
                "--run-dir",
                str(state.run_dir),
                "--consumer",
                "review",
            ]
        )
        == 0
    )
    received = json.loads(capsys.readouterr().out)
    assert received["acknowledged"]
    assert json.loads(state.read_text(received["retained_path"])) == received["event"]
    invalid = tmp_path / "invalid-subscription.json"
    invalid.write_text('{"unexpected":true}', encoding="utf-8")
    assert (
        main(
            [
                "coordination",
                "subscribe",
                "--run-dir",
                str(state.run_dir),
                "--consumer",
                "review",
                "--file",
                str(invalid),
            ]
        )
        == 2
    )
    assert "subscription file" in capsys.readouterr().err
