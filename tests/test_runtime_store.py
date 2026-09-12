"""Contention, fencing, crash rollback and budget invariants."""

import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from kdrx.runtime.store import SQLiteStore, StateConflict, wal_supported
from kdrx.schemas.plan import RunManifest
from kdrx.state import RunState


def test_stale_manifest_cannot_overwrite_other_process(tmp_path):
    state = RunState(tmp_path, "run")
    state.scaffold(
        RunManifest(run_id="run", plan_id="p", contract_id="c", route="R4", root_dir="")
    )
    stale = state.load_manifest()
    script = "from kdrx.state import RunState; import sys; s=RunState(sys.argv[1],'run'); m=s.load_manifest(); m.completed_tasks=['a']; s.save_manifest(m)"
    subprocess.run([sys.executable, "-c", script, str(tmp_path)], check=True)
    stale.completed_tasks = ["b"]
    with pytest.raises(StateConflict):
        state.save_manifest(stale)
    assert state.load_manifest().completed_tasks == ["a"]


def test_one_lease_wins(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    store.register_tasks("r", ["a"])

    def acquire(i):
        try:
            return store.claim("r", "a", str(i))
        except StateConflict:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(acquire, range(8)))
    assert sum(result is not None for result in results) == 1


def test_commit_rejects_kernel_owned_artifact_even_without_planner(tmp_path):
    store = SQLiteStore(tmp_path / "state.sqlite3")
    store.register_tasks("r", ["a"])
    lease = store.claim("r", "a", "worker")
    with pytest.raises(ValueError, match="kernel-owned"):
        store.finish(
            lease,
            {"run_id": "r", "task_id": "a", "attempt_id": lease["attempt_id"]},
            [{"path": "manifest.json", "sha256": "a" * 64, "size": 1}],
        )
    assert store.completed("r") == {} and store.artifacts("r", "a") == []


def test_expired_worker_cannot_publish(tmp_path):
    store = SQLiteStore(tmp_path / "db")
    store.register_tasks("r", ["a"])
    old = store.claim("r", "a", "old", 0.01)
    time.sleep(0.02)
    new = store.claim("r", "a", "new")
    assert new["fence"] > old["fence"]
    with pytest.raises(StateConflict):
        store.finish(
            old, {"run_id": "r", "task_id": "a", "attempt_id": old["attempt_id"]}, []
        )
    store.finish(
        new, {"run_id": "r", "task_id": "a", "attempt_id": new["attempt_id"]}, []
    )
    with pytest.raises(StateConflict):
        store.finish(
            old, {"run_id": "r", "task_id": "a", "attempt_id": old["attempt_id"]}, []
        )
    assert store.completed("r")["a"]["attempt_id"] == new["attempt_id"]
    assert len([e for e in store.events("r") if e["kind"] == "task_committed"]) == 1


def test_atomic_reservations_never_overbook(tmp_path):
    store = SQLiteStore(tmp_path / "db")
    store.configure_budget("r", "tokens", 10)

    def reserve(i):
        try:
            store.reserve("r", "tokens", 3, str(i))
            return str(i)
        except StateConflict:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(filter(lambda x: x is not None, pool.map(reserve, range(12))))
    assert len(accepted) == 3
    store.reconcile(accepted[0], None)
    store.reconcile(accepted[0], None)
    with store.connect() as db:
        row = db.execute("SELECT spent,reserved FROM budgets").fetchone()
        assert tuple(row) == (3, 6)


def test_kill_before_commit_rolls_back_and_backup_replays(tmp_path):
    path = tmp_path / "db"
    store = SQLiteStore(path)
    store.append_event("r", {"kind": "before"})
    script = (
        "from kdrx.runtime.store import SQLiteStore; import os,sys; s=SQLiteStore(sys.argv[1]); "
        "ctx=s.transaction(); db=ctx.__enter__(); s.event(db,'r',{'kind':'uncommitted'}); os._exit(9)"
    )
    assert subprocess.run([sys.executable, "-c", script, str(path)]).returncode == 9
    assert store.integrity_check()
    assert [e["kind"] for e in store.events("r")] == ["before"]
    store.backup(tmp_path / "backup")
    restored = SQLiteStore(tmp_path / "backup")
    assert restored.events("r") == store.events("r")


def test_wal_version_guard():
    assert not wal_supported((3, 49, 1))
    assert not wal_supported((3, 51, 2))
    assert wal_supported((3, 51, 3)) and wal_supported((3, 50, 7))
