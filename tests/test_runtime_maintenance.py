import time
from pathlib import Path

from kdrx.runtime.blobs import BlobStore
from kdrx.runtime.maintenance import collect_abandoned
from kdrx.runtime.store import SQLiteStore
from kdrx.runner import run_file_research
from kdrx.state import RunState
from kdrx.application.delivery import verify_delivery


def test_gc_quarantines_only_orphans_and_preserves_transitive_source_blobs(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "study.txt").write_text("Latency is 5 ms under load.", encoding="utf-8")
    summary = run_file_research(corpus, "latency under load", tmp_path / "runs")
    state = RunState(tmp_path / "runs", summary["run_id"])
    blobs = BlobStore(state.root / ".blobs")
    orphan = blobs.put(b"uncommitted orphan")
    preview = collect_abandoned(state.store, retention_seconds=0, now=time.time() + 1)
    assert blobs.path(orphan).exists() and preview["dry_run"]
    assert f".blobs/{orphan[:2]}/{orphan}" in preview["candidates"]
    assert len([p for p in preview["candidates"] if p.startswith(".staging/")]) == 4
    applied = collect_abandoned(
        state.store, retention_seconds=0, apply=True, now=time.time() + 1
    )
    assert not blobs.path(orphan).exists()
    assert (
        Path(applied["quarantine_root"]) / f".blobs/{orphan[:2]}/{orphan}"
    ).read_bytes() == b"uncommitted orphan"
    assert verify_delivery(state.run_dir)["deliverable"]


def test_gc_retains_new_and_running_attempt_blobs(tmp_path):
    store = SQLiteStore(tmp_path / ".kdr-state.sqlite3")
    blobs = BlobStore(tmp_path / ".blobs")
    orphan = blobs.put(b"still being produced")
    assert not collect_abandoned(store)["candidates"]
    store.register_tasks("r", ["a"])
    store.claim("r", "a", "worker")
    result = collect_abandoned(
        store, retention_seconds=0, now=time.time() + 1, apply=True
    )
    assert result["active_attempts"] == 1 and not result["candidates"]
    assert blobs.path(orphan).exists()
