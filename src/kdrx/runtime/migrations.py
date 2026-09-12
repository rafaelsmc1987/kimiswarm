"""Verified legacy snapshot import; old claims of success remain unverified."""

from __future__ import annotations

import io
import json
import os
import uuid
import zipfile
from pathlib import Path

from kdrx.schemas.plan import ResearchPlan, RunManifest
from kdrx.schemas.request import ResearchContract
from kdrx.schemas.versioning import migrate_legacy, normalize_artifact_path
from kdrx.security import has_symlink_component
from kdrx.state import CANONICAL_FILES, RunState, hash_bytes
from kdrx.runtime.store import StateConflict

MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024


def _snapshot(source: Path):
    source = Path(source).absolute()
    if has_symlink_component(source):
        raise ValueError("legacy source cannot traverse a link or junction")
    files = {}
    aliases = set()
    total = 0

    def accept(name, size, read):
        nonlocal total
        path = normalize_artifact_path(name)
        if path.casefold() in aliases:
            raise ValueError("legacy snapshot contains path aliases")
        aliases.add(path.casefold())
        total += size
        if total > MAX_SNAPSHOT_BYTES:
            raise ValueError("legacy snapshot exceeds 512 MiB import limit")
        data = read()
        if len(data) != size:
            raise ValueError("legacy file changed during snapshot")
        files[path] = data

    if source.is_dir():
        for path in sorted(source.rglob("*")):
            if has_symlink_component(path):
                raise ValueError("legacy snapshot contains a link or junction")
            if path.is_file():
                accept(
                    path.relative_to(source).as_posix(),
                    path.stat().st_size,
                    path.read_bytes,
                )
    elif source.is_file():
        with zipfile.ZipFile(source) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("legacy ZIP contains a symbolic link")
                accept(entry.filename, entry.file_size, lambda e=entry: archive.read(e))
    else:
        raise FileNotFoundError(source)
    required = {"manifest.json", "plan.json", "research_contract.json"}
    if not required <= files.keys():
        raise ValueError(
            "legacy snapshot is missing required files: "
            + ", ".join(sorted(required - files.keys()))
        )
    manifest = RunManifest.model_validate(
        migrate_legacy(json.loads(files["manifest.json"]))
    )
    payload = migrate_legacy(json.loads(files["plan.json"]))
    payload["tasks"] = [migrate_legacy(t) for t in payload.get("tasks", [])]
    plan = ResearchPlan.model_validate(payload)
    contract = ResearchContract.model_validate(
        migrate_legacy(json.loads(files["research_contract.json"]))
    )
    if (
        manifest.plan_id != plan.plan_id
        or manifest.contract_id != contract.contract_id
        or plan.contract_id != contract.contract_id
        or manifest.route != plan.route
        or plan.route != contract.route.value
    ):
        raise ValueError("legacy run/plan/contract identity mismatch")
    verified = 0
    for name, expected in manifest.artifact_hashes.items():
        relative = normalize_artifact_path(name)
        if relative not in files or hash_bytes(
            files[relative]
        ) != expected.removeprefix("sha256:"):
            raise ValueError(f"legacy artifact hash mismatch: {name}")
        verified += 1
    observed = {name: hash_bytes(data) for name, data in sorted(files.items())}
    digest = hash_bytes(json.dumps(observed, sort_keys=True).encode("utf-8"))
    return (
        files,
        manifest,
        plan,
        contract,
        {
            "run_id": manifest.run_id,
            "snapshot_hash": digest,
            "file_hashes": observed,
            "declared_hashes_verified": verified,
            "files_observed": len(files),
            "deliverable": False,
            "read_only": True,
            "limitation": "legacy completion and gates lack kernel attempt receipts; preserved as unverified history",
        },
    )


def inspect_legacy(source: Path) -> dict:
    """Read an old directory or backup ZIP without opening/initializing SQLite."""
    return _snapshot(source)[-1]


def _backup(files, destination: Path, digest: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if inspect_legacy(destination)["snapshot_hash"] != digest:
            raise ValueError("existing migration backup hash mismatch")
        return
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(zipfile.ZipInfo(name), data)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(buffer.getvalue())
            handle.flush()
            os.fsync(handle.fileno())
        if inspect_legacy(temporary)["snapshot_hash"] != digest:
            raise ValueError("migration backup verification failed")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def migrate_run(source: Path, runs_root: Path) -> dict:
    files, old, plan, contract, summary = _snapshot(source)
    state = RunState(runs_root, old.run_id)
    source = Path(source).absolute()
    if source.is_dir() and (state.root == source or source in state.root.parents):
        raise ValueError("migration destination must be outside the legacy source")
    if state.run_dir == source:
        raise ValueError("legacy original is read-only; choose another runs root")
    backup = (
        state.root
        / ".legacy-backups"
        / f"{state.run_id}-{summary['snapshot_hash']}.zip"
    )
    if has_symlink_component(backup):
        raise ValueError("migration backup cannot traverse a link or junction")
    _backup(files, backup, summary["snapshot_hash"])
    store = state.store
    with store.transaction() as db:
        row = db.execute(
            "SELECT payload FROM runs WHERE run_id=?", (state.run_id,)
        ).fetchone()
        if row is not None:
            prior = json.loads(row[0]).get("metadata", {}).get("migration", {})
            if prior.get("snapshot_hash") != summary["snapshot_hash"]:
                raise StateConflict("run identity already exists with another snapshot")
            result = {
                **summary,
                "backup": str(backup),
                "run_dir": str(state.run_dir),
                "already_imported": True,
            }
        else:
            if state.run_dir.exists() and any(state.run_dir.iterdir()):
                raise StateConflict("migration destination contains uncommitted files")
            state.run_dir.mkdir(parents=True, exist_ok=True)
            plan_bytes = plan.model_dump_json(indent=2).encode("utf-8")
            projected = {
                name: b""
                for name in CANONICAL_FILES
                if name not in {"manifest.json", "events.jsonl"}
            }
            projected.update(
                {f"legacy/files/{name}": data for name, data in files.items()}
            )
            projected.update(
                {
                    "plan.json": plan_bytes,
                    "plan.md": plan.plan_md.encode("utf-8"),
                    "research_contract.json": contract.model_dump_json(indent=2).encode(
                        "utf-8"
                    ),
                }
            )
            manifest = RunManifest(
                run_id=state.run_id,
                plan_id=plan.plan_id,
                contract_id=contract.contract_id,
                route=plan.route,
                root_dir=str(state.run_dir),
                state_revision=1,
                plan_revision=plan.plan_revision,
                artifact_hashes={
                    p: hash_bytes(data)
                    for p, data in projected.items()
                    if p != "delivery-manifest.json"
                },
                metadata={
                    "migration": {
                        **summary,
                        "backup": str(backup),
                        "legacy_completed_tasks": old.completed_tasks,
                        "legacy_status": old.status.value,
                    },
                    "plan": {
                        "sha256": hash_bytes(plan_bytes),
                        "revision": plan.plan_revision,
                        "source": "legacy-migration",
                        "review_approved": False,
                    },
                    "seal": {"eligible": False, "reason": "legacy_unverified"},
                },
            )
            encoded = manifest.model_dump_json(indent=2)
            db.execute("INSERT INTO runs VALUES(?,?,?)", (state.run_id, 1, encoded))
            store.record_plan(
                db, state.run_id, plan_bytes, manifest.model_dump(mode="json")
            )
            for relative, data in projected.items():
                store.project(db, state.run_id, relative, payload=data)
            store.project(
                db,
                state.run_id,
                "manifest.json",
                payload=(encoded + "\n").encode("utf-8"),
            )
            store.event(
                db,
                state.run_id,
                {
                    "kind": "legacy_snapshot_imported",
                    "snapshot_hash": summary["snapshot_hash"],
                    "verified_hash_count": summary["declared_hashes_verified"],
                    "delivery_eligible": False,
                },
            )
            result = {
                **summary,
                "backup": str(backup),
                "run_dir": str(state.run_dir),
                "already_imported": False,
            }
    state.flush_exports()
    return result
