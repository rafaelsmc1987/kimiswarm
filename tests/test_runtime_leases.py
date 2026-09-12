import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from kdrx.runtime.leases import LeaseKeeper
from kdrx.runtime.store import SQLiteStore, StateConflict
from kdrx.runner import (
    _FileResearchExecutor,
    build_contract,
    build_plan,
    execute_plan,
    prepare_run_dir,
)
from kdrx.retrieval import FileCorpus


def test_heartbeats_keep_the_original_attempt_alive(tmp_path):
    store = SQLiteStore(tmp_path / "db")
    store.register_tasks("r", ["a"])
    lease = store.claim("r", "a", "worker", seconds=0.5)
    keeper = LeaseKeeper(store, lease, seconds=0.5, interval=0.025).start()
    try:
        time.sleep(0.7)
        keeper.check()
        with pytest.raises(StateConflict):
            store.claim("r", "a", "competitor")
        store.finish(
            lease,
            {"run_id": "r", "task_id": "a", "attempt_id": lease["attempt_id"]},
            [],
        )
    finally:
        keeper.stop()
    assert not keeper._thread.is_alive()


def test_cancellation_from_another_connection_blocks_late_outputs(
    tmp_path, monkeypatch
):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "study.txt").write_text("Latency is 5 ms under load.", encoding="utf-8")
    contract = build_contract("latency under load")
    plan = build_plan(contract)
    state, _ = prepare_run_dir(plan, contract, tmp_path / "runs")
    started = threading.Event()
    original = _FileResearchExecutor.__call__

    def delayed(self, brief):
        started.set()
        assert self.state.cancelled.wait(5), "worker did not observe revoked lease"
        return original(self, brief)

    monkeypatch.setattr(_FileResearchExecutor, "__call__", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execute_plan, plan, contract, FileCorpus(corpus), state)
        assert started.wait(5)
        SQLiteStore(state.store.path).cancel_run(state.run_id)
        result, _ = future.result(timeout=15)
    assert result.failed and not result.completed and not result.deliverable
    assert state.load_manifest().status == "cancelled"
    assert state.read_text("corpus/sources.jsonl") == ""
    assert not state.store.completed(state.run_id)
    assert not state.load_manifest().metadata["seal"]["eligible"]
