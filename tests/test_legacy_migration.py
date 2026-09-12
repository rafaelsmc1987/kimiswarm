import json
from pathlib import Path

import pytest

from kdrx.runner import build_contract, build_plan, resume_run
from kdrx.retrieval import FileCorpus
from kdrx.runtime.migrations import inspect_legacy, migrate_run
from kdrx.runtime.store import ProjectionError, StateConflict
from kdrx.schemas.plan import RunManifest
from kdrx.state import RunState, hash_bytes


def legacy_run(tmp_path):
    directory = tmp_path / "old" / "legacy-run"
    directory.mkdir(parents=True)
    contract = build_contract("latency under load")
    plan = build_plan(contract)
    for name, value in (
        ("plan.json", plan.model_dump(mode="json")),
        ("research_contract.json", contract.model_dump(mode="json")),
    ):
        value.pop("schema_version")
        directory.joinpath(name).write_text(json.dumps(value), encoding="utf-8")
    directory.joinpath("report.md").write_bytes(b"legacy unverified report")
    manifest = RunManifest(
        run_id=directory.name,
        plan_id=plan.plan_id,
        contract_id=contract.contract_id,
        route=contract.route.value,
        root_dir=str(directory),
        status="succeeded",
        completed_tasks=[t.task_id for t in plan.tasks],
        gate_results={"integrity": "pass"},
        artifact_hashes={"report.md": hash_bytes(b"legacy unverified report")},
    ).model_dump(mode="json")
    manifest["schema_version"] = "0.2.0"
    directory.joinpath("manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return directory


def test_legacy_migration_preserves_original_and_never_synthesizes_success(tmp_path):
    source = legacy_run(tmp_path)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir()}
    result = migrate_run(source, tmp_path / "new")
    assert before == {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir()
    }
    state = RunState(tmp_path / "new", source.name)
    manifest = state.load_manifest()
    assert manifest.completed_tasks == [] and manifest.gate_results == {}
    assert state.store.completed(state.run_id) == {}
    assert manifest.metadata["migration"]["legacy_completed_tasks"]
    assert not manifest.metadata["seal"]["eligible"]
    assert (
        inspect_legacy(Path(result["backup"]))["snapshot_hash"]
        == result["snapshot_hash"]
    )
    assert not (source.parent / ".kdr-state.sqlite3").exists()
    assert migrate_run(source, tmp_path / "new")["already_imported"]
    with pytest.raises(ValueError, match="read-only"):
        resume_run(state, FileCorpus(tmp_path))
    with pytest.raises(StateConflict, match="read-only"):
        state.save_manifest(manifest)
    with pytest.raises(StateConflict, match="read-only"):
        state.write_text("legacy/files/report.md", "replacement")


@pytest.mark.parametrize("defect", ["hash", "version", "path", "identity"])
def test_invalid_legacy_snapshot_rejected_before_import(tmp_path, defect):
    source = legacy_run(tmp_path)
    path = source / "manifest.json"
    manifest = json.loads(path.read_bytes())
    if defect == "hash":
        (source / "report.md").write_bytes(b"corruption")
    elif defect == "version":
        manifest["schema_version"] = "9.0"
    elif defect == "path":
        manifest["artifact_hashes"] = {"../outside.txt": "a" * 64}
    else:
        manifest["plan_id"] = "other-plan"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        migrate_run(source, tmp_path / "new")
    assert not (tmp_path / "new" / ".kdr-state.sqlite3").exists()


def test_migration_export_failure_recovers_committed_import(tmp_path, monkeypatch):
    source = legacy_run(tmp_path)
    original = RunState._atomic_write

    def fail(self, path, data):
        raise OSError("disk full")

    monkeypatch.setattr(RunState, "_atomic_write", fail)
    with pytest.raises(ProjectionError):
        migrate_run(source, tmp_path / "new")
    monkeypatch.setattr(RunState, "_atomic_write", original)
    state = RunState(tmp_path / "new", source.name)
    assert state.load_manifest().metadata["migration"]["read_only"]
    assert (
        state._resolve("legacy/files/report.md").read_bytes()
        == b"legacy unverified report"
    )
    assert state.store.integrity_check()


def test_legacy_read_only_cli_does_not_initialize_database(tmp_path, capsys):
    from kdrx.cli import main

    source = legacy_run(tmp_path)
    assert main(["legacy-status", "--source", str(source)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["declared_hashes_verified"] == 1 and not output["deliverable"]
    assert not (source.parent / ".kdr-state.sqlite3").exists()


def test_migration_transaction_rollback_keeps_verified_backup_for_retry(
    tmp_path, monkeypatch
):
    from kdrx.runtime.store import SQLiteStore

    source = legacy_run(tmp_path)
    original = SQLiteStore.event

    def fail(db, run_id, event):
        if event.get("kind") == "legacy_snapshot_imported":
            raise OSError("interrupted transaction")
        return original(db, run_id, event)

    monkeypatch.setattr(SQLiteStore, "event", staticmethod(fail))
    with pytest.raises(OSError, match="interrupted"):
        migrate_run(source, tmp_path / "new")
    store = SQLiteStore(tmp_path / "new" / ".kdr-state.sqlite3")
    assert store.load_manifest(source.name) is None
    backup = next((tmp_path / "new" / ".legacy-backups").glob("*.zip"))
    assert inspect_legacy(backup)["declared_hashes_verified"] == 1
    monkeypatch.setattr(SQLiteStore, "event", staticmethod(original))
    assert not migrate_run(source, tmp_path / "new")["already_imported"]
