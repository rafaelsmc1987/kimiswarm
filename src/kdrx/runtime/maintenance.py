"""Conservative retention and reversible quarantine of abandoned runtime data."""

from __future__ import annotations

import json
import re
import time
import uuid

from kdrx.runtime.blobs import BlobStore
from kdrx.runtime.store import SQLiteStore
from kdrx.security import has_symlink_component, safe_join

_DIGEST = re.compile(rb"(?<![a-zA-Z0-9])[0-9a-f]{64}(?![a-zA-Z0-9])")


def collect_abandoned(
    store: SQLiteStore,
    *,
    retention_seconds: float = 7 * 86400,
    apply: bool = False,
    now: float | None = None,
) -> dict:
    """Inventory by default; --apply quarantines, never permanently deletes.

    All running attempts conservatively protect uncommitted blobs, including
    expired leases whose workers may still be alive. Unknown staging trees and
    temporary files are not claimed by this collector.
    """
    if retention_seconds < 0:
        raise ValueError("retention cannot be negative")
    root = store.path.parent
    blob_root, stage_root = root / ".blobs", root / ".staging"
    if any(has_symlink_component(p) for p in (root, blob_root, stage_root)):
        raise ValueError("maintenance roots cannot traverse links or junctions")
    cutoff = (time.time() if now is None else now) - retention_seconds
    with store.transaction() as db:
        active = db.execute(
            "SELECT COUNT(*) FROM attempts WHERE status='running'"
        ).fetchone()[0]
        blobs = {
            p.name: p
            for p in blob_root.glob("*/*")
            if p.is_file() and re.fullmatch(r"[0-9a-f]{64}", p.name)
        }
        for path in blobs.values():
            if has_symlink_component(path) or path.parent.name != path.name[:2]:
                raise ValueError("unexpected blob storage path")
        references = {
            row[0]
            for row in db.execute(
                "SELECT hash FROM artifacts UNION SELECT hash FROM file_projections"
            )
        }
        required = {
            row[0]
            for row in db.execute(
                "SELECT hash FROM artifacts UNION SELECT hash FROM file_projections WHERE payload IS NULL"
            )
        }
        if required - set(blobs):
            raise ValueError(
                "referenced blobs missing; recover storage before garbage collection"
            )
        for table, column in (
            ("runs", "payload"),
            ("file_projections", "payload"),
            ("deliveries", "payload"),
            ("plan_revisions", "payload"),
        ):
            for row in db.execute(
                f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"
            ):
                data = row[0].encode("utf-8") if isinstance(row[0], str) else row[0]
                references.update(match.decode() for match in _DIGEST.findall(data))
        reachable = set()
        pending = list(references & set(blobs))
        immutable = BlobStore(blob_root)
        while pending:
            digest = pending.pop()
            if digest in reachable:
                continue
            reachable.add(digest)
            data = immutable.get(digest)
            pending.extend(
                {match.decode() for match in _DIGEST.findall(data)}
                & set(blobs) - reachable
            )
        candidates = []
        if not active:
            candidates.extend(
                p
                for digest, p in blobs.items()
                if digest not in reachable and p.stat().st_mtime <= cutoff
            )
        attempts = db.execute(
            "SELECT attempt_id,run_id,status FROM attempts WHERE status!='running'"
        ).fetchall()
        for attempt in attempts:
            path = safe_join(stage_root, f"{attempt['run_id']}/{attempt['attempt_id']}")
            if not path.is_dir():
                continue
            members = [path, *path.rglob("*")]
            if any(has_symlink_component(member) for member in members):
                raise ValueError("abandoned staging contains a link or junction")
            if max(member.stat().st_mtime for member in members) <= cutoff:
                candidates.append(path)
        inventory = [p.relative_to(root).as_posix() for p in sorted(candidates)]
        result = {
            "dry_run": not apply,
            "retention_seconds": retention_seconds,
            "active_attempts": active,
            "candidates": inventory,
            "quarantined": [],
        }
        if apply and candidates:
            quarantine = safe_join(root, f".quarantine/{uuid.uuid4().hex}")
            if has_symlink_component(quarantine):
                raise ValueError("quarantine cannot traverse links")
            quarantine.mkdir(parents=True, exist_ok=False)
            (quarantine / "inventory.json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8"
            )
            for path in candidates:
                relative = path.relative_to(root).as_posix()
                destination = safe_join(quarantine, relative)
                allowed = blob_root if path.is_file() else stage_root
                # Validate final absolute paths immediately before every move.
                if (
                    not path.resolve().is_relative_to(allowed.resolve())
                    or not destination.resolve().is_relative_to(quarantine.resolve())
                    or has_symlink_component(path)
                    or has_symlink_component(destination)
                ):
                    raise ValueError("maintenance move escaped its owned root")
                destination.parent.mkdir(parents=True, exist_ok=True)
                path.rename(destination)
                result["quarantined"].append(relative)
            result["quarantine_root"] = str(quarantine)
            store.event(
                db,
                "runtime-maintenance",
                {"kind": "abandoned_data_quarantined", **result},
            )
        return result
