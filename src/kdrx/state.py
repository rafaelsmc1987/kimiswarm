"""Resumable run state and the persistent research artifact tree (plan §31, §40).

``RunState`` owns a single run directory under ``.research/runs/<run_id>/`` and
provides scaffolding, an append-only event log, content hashing, checkpointing
and resume. The directory layout is the one specified in §31.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from kdrx.schemas.plan import RunManifest
from kdrx.security import has_symlink_component, safe_join
from kdrx.schemas.versioning import validate_component, normalize_artifact_path

# Canonical subdirectories of a run (plan §31). Order matters for rendering.
RUN_SUBDIRS: tuple[str, ...] = (
    "tasks",
    "agents",
    "corpus/documents",
    "corpus/metadata",
    "corpus/indexes",
    "evidence/tables",
    "evidence/figures",
    "evidence/calculations",
    "claims",
    "analysis",
    "research",
    "retrieval",
    "writing",
    "reviews",
    "verification",
    "trace/sessions",
    "delivery",
)

CANONICAL_FILES: tuple[str, ...] = (
    "request.yaml",
    "research_contract.yaml",
    "plan.md",
    "manifest.json",
    "events.jsonl",
    "dag.json",
    "waves.json",
    "corpus/sources.jsonl",
    "evidence/spans.jsonl",
    "claims/claims.jsonl",
    "claims/edges.jsonl",
    "claims/contradictions.jsonl",
    "claims/standings.jsonl",
    "trace/exploration_tree.yaml",
    "trace/decisions.jsonl",
    "trace/dead_ends.jsonl",
    "delivery-manifest.json",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    """SHA-256 of a file's bytes (deterministic)."""
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_bytes(data: bytes) -> str:
    return _sha256(data)


def run_id_from_plan(plan_id: str, suffix: str | None = None) -> str:
    """Derive a stable run id from a plan id and an optional suffix.

    Uses integer time for ordering; the run id is intentionally monotonic and
    human-sortable (``run-<epoch>-<plan-slug>``).
    """
    slug = "".join(c if c.isalnum() else "-" for c in plan_id).strip("-").lower()
    base = f"run-{int(time.time())}-{slug[:48]}-{uuid.uuid4().hex}"
    return validate_component(f"{base}-{suffix}" if suffix else base)


class RunState:
    """Owns one run directory and its manifest.

    T-04-05: todo write é (a) resolvido via ``safe_join`` (nenhum rel_path
    escapa do run dir; ``..``/absoluto levanta) e (b) atômico
    (tmp + ``os.replace`` no mesmo diretório). Um lock por instância serializa
    manifest/events/writes deste processo — o scheduler ainda é sequencial,
    mas crash entre write parcial e rename nunca deixa arquivo truncado.
    """

    def __init__(self, root: str | Path, run_id: str) -> None:
        self.root = Path(root).absolute()
        self.run_id = validate_component(run_id)
        candidate = self.root / self.run_id
        if has_symlink_component(candidate):
            raise ValueError("run directory cannot traverse a link or junction")
        self.run_dir = safe_join(self.root, self.run_id)
        self._lock = threading.Lock()
        self._tmp_counter = 0
        self._store_instance = None

    @property
    def store(self):
        from kdrx.runtime.store import SQLiteStore

        if self._store_instance is None:
            self._store_instance = SQLiteStore(self.root / ".kdr-state.sqlite3")
        return self._store_instance

    def _resolve(self, rel_path: str) -> Path:
        rel_path = normalize_artifact_path(rel_path)
        if has_symlink_component(self.run_dir / rel_path):
            raise ValueError("artifact cannot traverse a link or junction")
        return safe_join(self.run_dir, rel_path)

    def _atomic_write(self, path: Path, content: str | bytes) -> Path:
        self._tmp_counter += 1
        tmp = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
        try:
            with tmp.open("xb") as fh:
                fh.write(
                    content.encode("utf-8") if isinstance(content, str) else content
                )
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)  # atômico dentro do mesmo diretório
        finally:
            tmp.unlink(missing_ok=True)
        return path

    # ------------------------------------------------------------------ paths
    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "manifest.json"

    @property
    def events_path(self) -> Path:
        return self.run_dir / "events.jsonl"

    # ----------------------------------------------------------------- scaffold
    def scaffold(self, manifest: RunManifest) -> Path:
        """Create the canonical directory tree and write the initial manifest."""
        if manifest.run_id != self.run_id:
            raise ValueError("manifest run identity mismatch")
        self.run_dir.mkdir(parents=True, exist_ok=False)
        for sub in RUN_SUBDIRS:
            (self.run_dir / sub).mkdir(parents=True, exist_ok=True)
        for f in CANONICAL_FILES:
            path = self.run_dir / f
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
        manifest.root_dir = str(self.run_dir)
        self.commit_bundle(
            manifest,
            {
                relative: ""
                for relative in CANONICAL_FILES
                if relative != "manifest.json"
            },
        )
        self.append_event({"kind": "run_created", "run_id": self.run_id})
        return self.run_dir

    # ---------------------------------------------------------------- manifest
    def save_manifest(self, manifest: RunManifest) -> None:
        if manifest.run_id != self.run_id:
            raise ValueError("manifest run identity mismatch")
        manifest.updated_at = datetime.now(timezone.utc)
        with self._lock:
            manifest.state_revision = self.store.save_manifest(
                manifest.model_dump(mode="json"),
            )
            self.flush_exports()

    def commit_bundle(
        self, manifest: RunManifest, files: dict[str, str | bytes]
    ) -> None:
        """Commit the checkpoint and its recoverable exports in one transaction."""
        if manifest.run_id != self.run_id:
            raise ValueError("manifest run identity mismatch")
        manifest.updated_at = datetime.now(timezone.utc)

        for rel in files:
            self._resolve(rel)
        with self._lock:
            manifest.state_revision = self.store.save_manifest(
                manifest.model_dump(mode="json"),
                {
                    rel: data.encode("utf-8") if isinstance(data, str) else data
                    for rel, data in files.items()
                },
            )
            self.flush_exports()

    def flush_exports(self) -> None:
        def export(relative, data):
            path = self._resolve(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(path, data)

        self.store.flush_projections(self.run_id, export)

    def rebuild_exports(self) -> None:
        """Regenerate database-owned files after an explicit recovery request."""
        self.store.rebuild_projections(self.run_id)
        self.flush_exports()

    def load_manifest(self) -> RunManifest:
        if (self.root / ".kdr-state.sqlite3").is_file():
            self.flush_exports()
        payload = (
            self.store.load_manifest(self.run_id)
            if (self.root / ".kdr-state.sqlite3").is_file()
            else None
        )
        if payload is None:
            if not self.manifest_path.exists():
                raise FileNotFoundError(f"no manifest at {self.manifest_path}")
            manifest = RunManifest.model_validate_json(
                self.manifest_path.read_text(encoding="utf-8")
            )
        else:
            manifest = RunManifest.model_validate(payload)
        if (
            manifest.run_id != self.run_id
            or Path(manifest.root_dir).resolve() != self.run_dir
        ):
            raise ValueError("manifest run directory identity mismatch")
        return manifest

    # ------------------------------------------------------------------ events
    def append_event(self, event: dict[str, Any]) -> None:
        """Append one event to the append-only log (JSON Lines, locked)."""
        record = dict(event)
        record.setdefault("ts", int(time.time()))
        with self._lock:
            self.store.append_event(self.run_id, record)
            self.flush_exports()

    def iter_events(self) -> Iterator[dict[str, Any]]:
        if (self.root / ".kdr-state.sqlite3").is_file():
            yield from self.store.events(self.run_id)
            return
        if not self.events_path.exists():
            return
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)

    # ----------------------------------------------------------------- hashing
    def snapshot_hashes(self) -> dict[str, str]:
        """Hash every file under the run dir, keyed by relative path."""
        out: dict[str, str] = {}
        for path in sorted(self.run_dir.rglob("*")):
            if path.is_file():
                out[path.relative_to(self.run_dir).as_posix()] = hash_file(
                    self._resolve(path.relative_to(self.run_dir).as_posix())
                )
        return out

    def verify_hashes(self, expected: dict[str, str]) -> list[str]:
        """Return the list of relative paths whose hash changed or went missing."""
        current = self.snapshot_hashes()
        bad: list[str] = []
        for rel, want in expected.items():
            rel = rel.replace("\\", "/")
            if rel not in current:
                bad.append(f"{rel} (missing)")
            elif current[rel] != want:
                bad.append(f"{rel} (changed)")
        return bad

    # ------------------------------------------------------------------ resume
    def resume(self) -> RunManifest:
        """Load the manifest and rebuild the not-yet-complete task set.

        This mirrors ``/kdr:resume``: it does not re-run anything, it only
        verifies hashes and returns a manifest whose ``completed_tasks`` /
        ``failed_tasks`` reflect the persisted state.
        """
        manifest = self.load_manifest()
        if manifest.artifact_hashes:
            changed = self.verify_hashes(manifest.artifact_hashes)
            if changed:
                manifest.metadata["hash_mismatch"] = changed
        return manifest

    # ---------------------------------------------------------------- helpers
    def write_text(self, rel_path: str, content: str) -> Path:
        if (self.root / ".kdr-state.sqlite3").is_file():
            payload = self.store.load_manifest(self.run_id)
            if payload:
                self.store.assert_writable(payload)
        path = self._resolve(rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            return self._atomic_write(path, content)

    def read_text(self, rel_path: str) -> str:
        return self._resolve(rel_path).read_text(encoding="utf-8")


def load_manifest_from_dir(run_dir: str | Path) -> RunManifest:
    """Convenience: load a manifest from an explicit run directory."""
    run_dir = Path(run_dir)
    return RunState(run_dir.absolute().parent, run_dir.name).load_manifest()
