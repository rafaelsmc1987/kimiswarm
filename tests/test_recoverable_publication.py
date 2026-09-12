"""Crash boundaries must preserve committed state and reject partial publication."""

import json
import subprocess
import sys

import pytest

from kdrx.runner import (
    _FileResearchExecutor,
    build_contract,
    build_plan,
    execute_plan,
    prepare_run_dir,
    resume_run,
)
from kdrx.retrieval import FileCorpus
from kdrx.state import RunState


def scaffold(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "study.txt").write_text("Latency is 5 ms under load.", encoding="utf-8")
    contract = build_contract("latency under load")
    plan = build_plan(contract)
    state, _ = prepare_run_dir(plan, contract, tmp_path / "runs")
    return FileCorpus(corpus), plan, contract, state


def test_committed_manifest_recovers_after_disk_export_failure(tmp_path, monkeypatch):
    _, _, _, state = scaffold(tmp_path)
    manifest = state.load_manifest()
    manifest.metadata["durable_marker"] = "committed-before-export"
    monkeypatch.setattr(
        state, "_atomic_write", lambda *a: (_ for _ in ()).throw(OSError("disk full"))
    )
    with pytest.raises(OSError):
        state.save_manifest(manifest)
    reopened = RunState(state.root, state.run_id)
    assert (
        reopened.load_manifest().metadata["durable_marker"] == "committed-before-export"
    )
    assert (
        json.loads(reopened.manifest_path.read_bytes())["metadata"]["durable_marker"]
        == "committed-before-export"
    )


def test_failed_attempt_cannot_modify_published_outputs(tmp_path, monkeypatch):
    corpus, plan, contract, state = scaffold(tmp_path)
    before = state.read_text("corpus/sources.jsonl")

    def fail(self, brief):
        self.state.write_text("corpus/sources.jsonl", "uncommitted bytes")
        raise ValueError("provider or validation failed")

    monkeypatch.setattr(_FileResearchExecutor, "__call__", fail)
    result, _ = execute_plan(plan, contract, corpus, state)
    assert result.failed and not result.completed
    assert state.read_text("corpus/sources.jsonl") == before


def test_kill_after_task_commit_resumes_without_repeating_retrieval(tmp_path):
    corpus, _, _, state = scaffold(tmp_path)
    script = """
import os,sys
from kdrx.runner import *
from kdrx.runtime.store import SQLiteStore
from kdrx.state import RunState
from kdrx.retrieval import FileCorpus
s=RunState(sys.argv[1],sys.argv[2])
p=ResearchPlan.model_validate_json(s.read_text('plan.json'))
c=ResearchContract.model_validate_json(s.read_text('research_contract.json'))
original=SQLiteStore.finish
def finish(self,lease,*args,**kwargs):
    result=original(self,lease,*args,**kwargs)
    if lease['task_id']=='T-RETRIEVE' and kwargs.get('success',True):os._exit(91)
    return result
SQLiteStore.finish=finish
execute_plan(p,c,FileCorpus(sys.argv[3]),s)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(state.root), state.run_id, str(corpus.root)],
        capture_output=True,
    )
    assert child.returncode == 91, child.stderr
    reopened = RunState(state.root, state.run_id)
    result, executor = resume_run(reopened, corpus)
    assert not result.failed and executor.sources
    assert not any(
        e["kind"] == "task_started" and e["task_id"] == "T-RETRIEVE"
        for e in result.events
    )
    assert (
        len(
            [
                e
                for e in reopened.iter_events()
                if e["kind"] == "task_committed" and e["task_id"] == "T-RETRIEVE"
            ]
        )
        == 1
    )


def test_completed_resume_changes_no_files_or_checkpoint(tmp_path):
    corpus, plan, contract, state = scaffold(tmp_path)
    execute_plan(plan, contract, corpus, state)
    before = {
        str(p): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in state.run_dir.rglob("*")
        if p.is_file()
    }
    revision = state.load_manifest().state_revision
    (corpus.root / "study.txt").write_text(
        "The corpus has changed completely.", encoding="utf-8"
    )
    result, executor = resume_run(
        RunState(state.root, state.run_id), FileCorpus(corpus.root)
    )
    assert result.deliverable and result.events == []
    assert executor.sources and "Latency" in executor.report_text
    assert state.load_manifest().state_revision == revision
    assert {
        str(p): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in state.run_dir.rglob("*")
        if p.is_file()
    } == before


def test_disk_full_after_success_does_not_retry_committed_task(tmp_path, monkeypatch):
    from kdrx.runtime.store import ProjectionError

    corpus, plan, contract, state = scaffold(tmp_path)
    original = state._atomic_write

    def disk_full(path, content):
        if path.name == "sources.jsonl":
            raise OSError("disk full")
        return original(path, content)

    monkeypatch.setattr(state, "_atomic_write", disk_full)
    with pytest.raises(ProjectionError):
        execute_plan(plan, contract, corpus, state)
    assert list(state.store.completed(state.run_id)) == ["T-RETRIEVE"]
    assert (
        len(
            [
                e
                for e in state.store.events(state.run_id)
                if e["kind"] == "lease_acquired"
            ]
        )
        == 1
    )
    result, _ = resume_run(RunState(state.root, state.run_id), corpus)
    assert result.deliverable


def test_undeclared_direct_write_is_rejected_before_publication(tmp_path, monkeypatch):
    corpus, plan, contract, state = scaffold(tmp_path)
    original = _FileResearchExecutor.__call__

    def rogue(self, brief):
        result = original(self, brief)
        (self.state.run_dir / "unclaimed.txt").write_text("not owned", encoding="utf-8")
        return result

    monkeypatch.setattr(_FileResearchExecutor, "__call__", rogue)
    result, _ = execute_plan(plan, contract, corpus, state)
    assert result.failed and not result.completed
    assert not (state.run_dir / "unclaimed.txt").exists()
    assert not state.store.completed(state.run_id)


def test_acknowledged_tampering_is_never_silently_repaired(tmp_path):
    corpus, plan, contract, state = scaffold(tmp_path)
    execute_plan(plan, contract, corpus, state)
    state.write_text("claims/standings.jsonl", '{"corrupt": true}\n')
    with pytest.raises(ValueError, match="hash mismatch"):
        resume_run(RunState(state.root, state.run_id), corpus)
    assert "corrupt" in state.read_text("claims/standings.jsonl")


def test_typed_checkpoint_rejects_duplicate_source_identity(tmp_path):
    from kdrx.application.checkpoints import load_checkpoint

    corpus, plan, contract, state = scaffold(tmp_path)
    execute_plan(plan, contract, corpus, state)
    original = state.read_text("corpus/sources.jsonl")
    state.write_text("corpus/sources.jsonl", original + original)
    with pytest.raises(ValueError, match="duplicate source_id"):
        load_checkpoint(state)


def test_backup_restores_committed_exports_and_keeps_blobs(tmp_path):
    from kdrx.runtime.store import SQLiteStore

    corpus, plan, contract, state = scaffold(tmp_path)
    execute_plan(plan, contract, corpus, state)
    original = state._resolve("corpus/sources.jsonl").read_bytes()
    backup = state.root / "backup.sqlite3"
    state.store.backup(backup)
    for path in state.run_dir.rglob("*"):
        if path.is_file():
            path.unlink()  # Only this test's exclusively created run directory.
    # Restore the database snapshot against the retained immutable blob store.
    state._store_instance = SQLiteStore(backup)
    state.rebuild_exports()
    assert state._resolve("corpus/sources.jsonl").read_bytes() == original
    assert state.store.integrity_check()
    assert not state.verify_hashes(state.load_manifest().artifact_hashes)
    with state.store.connect() as db:
        for row in db.execute(
            "SELECT path,hash FROM file_projections WHERE run_id=?", (state.run_id,)
        ):
            from kdrx.state import hash_file

            assert hash_file(state._resolve(row["path"])) == row["hash"]


def test_delivery_and_checkpoint_recover_together_after_export_failure(
    tmp_path, monkeypatch
):
    from kdrx.application.delivery import verify_delivery
    from kdrx.runtime.store import ProjectionError

    corpus, plan, contract, state = scaffold(tmp_path)
    original = state._atomic_write

    def disk_full(path, content):
        if path.name == "delivery-manifest.json":
            raise OSError("disk full during publication")
        return original(path, content)

    monkeypatch.setattr(state, "_atomic_write", disk_full)
    with pytest.raises(ProjectionError):
        execute_plan(plan, contract, corpus, state)
    reopened = RunState(state.root, state.run_id)
    result, _ = resume_run(reopened, corpus)
    assert result.deliverable and not result.events
    assert verify_delivery(reopened.run_dir)["deliverable"]
    assert reopened.load_manifest().metadata["seal"]["eligible"] is True
    with reopened.store.connect() as db:
        assert (
            db.execute(
                "SELECT eligible FROM deliveries WHERE run_id=?", (state.run_id,)
            ).fetchone()[0]
            == 1
        )


def test_distinct_process_commits_do_not_lose_checkpoints(tmp_path):
    _, _, _, state = scaffold(tmp_path)
    state.store.register_tasks(state.run_id, ["a", "b"])
    code = """
import sys
from kdrx.state import RunState
s=RunState(sys.argv[1], sys.argv[2])
lease=s.store.claim(s.run_id, sys.argv[3], sys.argv[3])
m=s.load_manifest()
s.store.finish(lease, {'run_id':s.run_id,'task_id':sys.argv[3],'attempt_id':lease['attempt_id'],'plan_id':m.plan_id,'plan_revision':0}, [], checkpoint={'plan_hash':m.metadata['plan']['sha256'], 'input_hashes':{}})
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(state.root), state.run_id, tid],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for tid in ["a", "b"]
    ]
    for process in processes:
        _, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stderr
    reopened = RunState(state.root, state.run_id)
    assert set(reopened.load_manifest().completed_tasks) == {"a", "b"}
    assert (
        len([e for e in reopened.iter_events() if e["kind"] == "task_committed"]) == 2
    )


def test_kill_between_blob_write_and_commit_leaves_only_recoverable_orphans(tmp_path):
    from kdrx.runtime.maintenance import collect_abandoned
    import time

    corpus, _, _, state = scaffold(tmp_path)
    script = """
import os,sys
from kdrx.runner import *
from kdrx.runtime.store import SQLiteStore
from kdrx.state import RunState
from kdrx.retrieval import FileCorpus
s=RunState(sys.argv[1],sys.argv[2])
p=ResearchPlan.model_validate_json(s.read_text('plan.json'))
c=ResearchContract.model_validate_json(s.read_text('research_contract.json'))
original=SQLiteStore.finish
def finish(self,lease,*args,**kwargs):
    if kwargs.get('success',True):
        with self.transaction() as db:
            db.execute('UPDATE tasks SET lease_until=0 WHERE run_id=? AND task_id=?',(lease['run_id'],lease['task_id']))
        os._exit(94)
    return original(self,lease,*args,**kwargs)
SQLiteStore.finish=finish
execute_plan(p,c,FileCorpus(sys.argv[3]),s)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(state.root), state.run_id, str(corpus.root)],
        capture_output=True,
    )
    assert child.returncode == 94, child.stderr
    reopened = RunState(state.root, state.run_id)
    assert not reopened.load_manifest().completed_tasks
    assert not reopened.store.completed(reopened.run_id)
    assert reopened.read_text("corpus/sources.jsonl") == ""
    assert reopened.store.reconcile_expired(reopened.run_id) == 1
    inventory = collect_abandoned(
        reopened.store, retention_seconds=0, now=time.time() + 1
    )
    assert any(p.startswith(".blobs/") for p in inventory["candidates"])
    assert any(p.startswith(".staging/") for p in inventory["candidates"])
    result, _ = resume_run(reopened, corpus)
    assert result.deliverable
    with reopened.store.connect() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM attempts WHERE run_id=? AND status='expired'",
                (reopened.run_id,),
            ).fetchone()[0]
            == 1
        )
