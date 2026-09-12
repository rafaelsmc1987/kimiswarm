"""Transactional SQLite state, task leases, fencing, reservations and replay."""

from __future__ import annotations

import json
import hashlib
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from datetime import datetime, timezone


class StateConflict(ValueError):
    """The caller's revision or lease is no longer authoritative."""

    code = "state_conflict"


class ProjectionError(OSError):
    """The transaction committed; retry publication, never the task itself."""

    committed = True


def wal_supported(version: tuple[int, ...] = sqlite3.sqlite_version_info) -> bool:
    return (
        version >= (3, 51, 3)
        or (3, 50, 7) <= version < (3, 51)
        or (3, 44, 6) <= version < (3, 45)
    )


class SQLiteStore:
    """Local disk only; old SQLite uses rollback journaling, never unsafe WAL."""

    def __init__(self, path: Path, *, journal: str = "auto") -> None:
        from kdrx.security import has_symlink_component

        self.path = Path(path).absolute()
        if has_symlink_component(self.path):
            raise ValueError("database cannot traverse a link or junction")
        if str(self.path).startswith("\\\\"):
            raise ValueError("SQLite runtime requires a local disk")
        if journal not in {"auto", "wal", "delete"}:
            raise ValueError("invalid journal mode")
        if journal == "wal" and not wal_supported():
            raise ValueError(
                f"SQLite {sqlite3.sqlite_version} lacks the required WAL-reset fix"
            )
        self.journal = "wal" if journal != "delete" and wal_supported() else "delete"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migration_backup = None
        with self.connect() as db:
            current = db.execute("PRAGMA user_version").fetchone()[0]
            if current not in {0, 1, 2, 3}:
                raise ValueError(f"unsupported database schema version {current}")
            if current in {1, 2}:
                folder = self.path.parent / ".schema-backups"
                if has_symlink_component(folder):
                    raise ValueError(
                        "migration backup cannot traverse a link or junction"
                    )
                folder.mkdir(exist_ok=True)
                self.migration_backup = (
                    folder / f"{self.path.name}.v{current}.{uuid.uuid4().hex}.sqlite3"
                )
                self.backup(self.migration_backup)
                with closing(sqlite3.connect(self.migration_backup)) as backup:
                    if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError(
                            "schema migration backup failed integrity verification"
                        )
            # journal_mode does not reliably honor busy_timeout while another
            # process is converting a newly created database to WAL.
            deadline = time.monotonic() + 30
            while True:
                try:
                    actual = db.execute("PRAGMA journal_mode").fetchone()[0]
                    if actual != self.journal:
                        actual = db.execute(
                            f"PRAGMA journal_mode={self.journal}"
                        ).fetchone()[0]
                    break
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower() or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            if actual != self.journal:
                raise ValueError(f"journal mode unavailable: {actual}")
            db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS plan_revisions(run_id TEXT NOT NULL, revision INTEGER NOT NULL, hash TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,revision));
                CREATE TABLE IF NOT EXISTS tasks(run_id TEXT NOT NULL, task_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', fence INTEGER NOT NULL DEFAULT 0,
                    worker_id TEXT, attempt_id TEXT, lease_until REAL, result TEXT, PRIMARY KEY(run_id,task_id));
                CREATE TABLE IF NOT EXISTS attempts(attempt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, task_id TEXT NOT NULL, fence INTEGER NOT NULL, status TEXT NOT NULL, started REAL NOT NULL, finished REAL);
                CREATE TABLE IF NOT EXISTS events(run_id TEXT NOT NULL, seq INTEGER NOT NULL, event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,seq));
                CREATE TABLE IF NOT EXISTS artifacts(run_id TEXT NOT NULL, task_id TEXT NOT NULL, path TEXT NOT NULL, hash TEXT NOT NULL, size INTEGER NOT NULL, attempt_id TEXT NOT NULL, PRIMARY KEY(run_id,task_id,path));
                CREATE TABLE IF NOT EXISTS sessions(session_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS budgets(run_id TEXT NOT NULL, dimension TEXT NOT NULL, ceiling REAL, spent REAL NOT NULL DEFAULT 0, reserved REAL NOT NULL DEFAULT 0, PRIMARY KEY(run_id,dimension));
                CREATE TABLE IF NOT EXISTS reservations(reservation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, dimension TEXT NOT NULL, amount REAL NOT NULL, actual REAL, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS deliveries(run_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, eligible INTEGER NOT NULL, PRIMARY KEY(run_id,revision));
                CREATE TABLE IF NOT EXISTS file_projections(run_id TEXT NOT NULL, path TEXT NOT NULL, hash TEXT NOT NULL, payload BLOB, generation INTEGER NOT NULL, exported_generation INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(run_id,path));
                CREATE TABLE IF NOT EXISTS coordination_policies(run_id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS coordination_messages(message_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,revision INTEGER NOT NULL,semantic_key TEXT NOT NULL,request_hash TEXT NOT NULL,event_id TEXT NOT NULL,created REAL NOT NULL,UNIQUE(run_id,revision,semantic_key));
                CREATE TABLE IF NOT EXISTS subscriptions(run_id TEXT NOT NULL,consumer_id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(run_id,consumer_id));
                CREATE TABLE IF NOT EXISTS notifications(run_id TEXT NOT NULL,consumer_id TEXT NOT NULL,event_id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,token TEXT,worker_id TEXT,lease_until REAL,available_at REAL NOT NULL DEFAULT 0,last_error TEXT,PRIMARY KEY(run_id,consumer_id,event_id));
                CREATE TABLE IF NOT EXISTS notification_inbox(run_id TEXT NOT NULL,consumer_id TEXT NOT NULL,event_id TEXT NOT NULL,processed REAL NOT NULL,PRIMARY KEY(run_id,consumer_id,event_id));
                CREATE INDEX IF NOT EXISTS notification_ready ON notifications(run_id,consumer_id,status,available_at);
                CREATE TABLE IF NOT EXISTS resource_locks(resource TEXT PRIMARY KEY,run_id TEXT NOT NULL,task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,token TEXT NOT NULL,fence INTEGER NOT NULL,lease_until REAL NOT NULL);
                PRAGMA user_version=3;
                COMMIT;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA busy_timeout=30000")
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def project(
        db,
        run_id: str,
        path: str,
        *,
        payload: bytes | None = None,
        digest: str | None = None,
    ) -> None:
        if payload is None and digest is None:
            raise ValueError("projection requires durable bytes or a blob digest")
        if payload is not None:
            actual = hashlib.sha256(payload).hexdigest()
            if digest is not None and digest != actual:
                raise ValueError("projection digest mismatch")
            digest = actual
        db.execute(
            "INSERT INTO file_projections VALUES(?,?,?,?,1,0) ON CONFLICT(run_id,path) DO UPDATE SET hash=excluded.hash,payload=excluded.payload,generation=file_projections.generation+1",
            (run_id, path, digest, payload),
        )

    def flush_projections(self, run_id: str, export) -> None:
        """Replay only unacknowledged exports; acknowledged tampering stays visible.

        The writer lock covers export and acknowledgement so an older exporter
        cannot overwrite a newer generation. A crash between them is replayable.
        """
        from kdrx.runtime.blobs import BlobStore

        try:
            with self.transaction() as db:
                rows = db.execute(
                    "SELECT * FROM file_projections WHERE run_id=? AND generation>exported_generation ORDER BY path",
                    (run_id,),
                ).fetchall()
                for row in rows:
                    data = row["payload"]
                    if data is None:
                        data = BlobStore(self.path.parent / ".blobs").get(row["hash"])
                    if hashlib.sha256(data).hexdigest() != row["hash"]:
                        raise ValueError("projection integrity hash mismatch")
                    export(row["path"], data)
                    db.execute(
                        "UPDATE file_projections SET exported_generation=generation WHERE run_id=? AND path=?",
                        (run_id, row["path"]),
                    )
        except (OSError, ValueError, sqlite3.Error) as exc:
            raise ProjectionError(
                "committed exports pending; repair storage and resume"
            ) from exc

    def rebuild_projections(self, run_id: str) -> None:
        """Explicit disaster recovery; ordinary resume never repairs tampering."""
        with self.transaction() as db:
            if (
                db.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone()
                is None
            ):
                raise StateConflict("unknown run for export recovery")
            self.event(db, run_id, {"kind": "exports_rebuild_requested"})
            db.execute(
                "UPDATE file_projections SET exported_generation=0 WHERE run_id=?",
                (run_id,),
            )

    @staticmethod
    def event(db, run_id: str, event: dict) -> dict:
        seq = db.execute(
            "SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE run_id=?", (run_id,)
        ).fetchone()[0]
        record = {
            **event,
            "run_id": run_id,
            "seq": seq,
            "event_id": uuid.uuid4().hex,
            "ts": time.time(),
        }
        db.execute(
            "INSERT INTO events VALUES(?,?,?,?)",
            (run_id, seq, record["event_id"], json.dumps(record)),
        )
        rows = db.execute(
            "SELECT payload FROM events WHERE run_id=? ORDER BY seq", (run_id,)
        ).fetchall()
        SQLiteStore.project(
            db,
            run_id,
            "events.jsonl",
            payload="".join(row[0] + "\n" for row in rows).encode("utf-8"),
        )
        from kdrx.runtime.notifications import enqueue_event

        enqueue_event(db, run_id, record)
        return record

    def append_event(self, run_id: str, event: dict) -> dict:
        with self.transaction() as db:
            row = db.execute(
                "SELECT payload FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row:
                self.assert_writable(json.loads(row[0]))
            return self.event(db, run_id, event)

    def events(self, run_id: str) -> list[dict]:
        with self.connect() as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT payload FROM events WHERE run_id=? ORDER BY seq", (run_id,)
                )
            ]

    def load_manifest(self, run_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def save_manifest(
        self, payload: dict, files: dict[str, bytes] | None = None
    ) -> int:
        run_id = payload["run_id"]
        expected = payload.get("state_revision", 0)
        with self.transaction() as db:
            row = db.execute(
                "SELECT revision,payload FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            current = row[0] if row else 0
            if row:
                self.assert_writable(json.loads(row[1]))
            if current != expected:
                raise StateConflict("manifest revision changed; reload before updating")
            payload = {**payload, "state_revision": current + 1}
            encoded = json.dumps(payload, ensure_ascii=False, indent=2)
            db.execute(
                "INSERT INTO runs VALUES(?,?,?) ON CONFLICT(run_id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload",
                (run_id, current + 1, encoded),
            )
            if (files or {}).get("plan.json"):
                self.record_plan(db, run_id, files["plan.json"], payload)
            for path, data in (files or {}).items():
                self.project(db, run_id, path, payload=data)
            if files and files.get("delivery-manifest.json", b"").strip():
                from kdrx.schemas.artifact import DeliveryManifest

                delivery = DeliveryManifest.model_validate_json(
                    files["delivery-manifest.json"]
                )
                revision = db.execute(
                    "SELECT COALESCE(MAX(revision),0)+1 FROM deliveries WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
                db.execute(
                    "INSERT INTO deliveries VALUES(?,?,?,?)",
                    (
                        run_id,
                        revision,
                        delivery.model_dump_json(),
                        int(delivery.is_complete()),
                    ),
                )
                self.event(
                    db,
                    run_id,
                    {
                        "kind": "delivery_checkpoint_committed",
                        "revision": revision,
                        "eligible": delivery.is_complete(),
                        "report_hash": delivery.verified_report_hash,
                    },
                )
            self.project(
                db, run_id, "manifest.json", payload=(encoded + "\n").encode("utf-8")
            )
            return current + 1

    def register_tasks(self, run_id: str, task_ids: list[str]) -> None:
        with self.transaction() as db:
            db.executemany(
                "INSERT OR IGNORE INTO tasks(run_id,task_id) VALUES(?,?)",
                [(run_id, tid) for tid in task_ids],
            )

    def transition(
        self, run_id: str, event: dict, *, expected_revision: int | None = None
    ) -> dict:
        """Merge lifecycle failure state without overwriting another task's commit."""
        with self.transaction() as db:
            row = db.execute(
                "SELECT payload FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise StateConflict("missing run")
            payload = json.loads(row[0])
            self.assert_writable(payload)
            if (
                expected_revision is not None
                and payload.get("metadata", {}).get("plan", {}).get("revision")
                != expected_revision
            ):
                raise StateConflict("event plan revision changed")
            tid = event.get("task_id")
            task = db.execute(
                "SELECT status FROM tasks WHERE run_id=? AND task_id=?", (run_id, tid)
            ).fetchone()
            if (
                event.get("kind") in {"task_exhausted", "task_blocked"}
                and task
                and task[0] not in {"succeeded", "running", "cancelled"}
                and tid not in payload["failed_tasks"]
            ):
                payload["failed_tasks"].append(tid)
                payload["state_revision"] += 1
                payload["updated_at"] = datetime.now(timezone.utc).isoformat()
                encoded = json.dumps(payload, ensure_ascii=False, indent=2)
                db.execute(
                    "UPDATE runs SET revision=?,payload=? WHERE run_id=?",
                    (payload["state_revision"], encoded, run_id),
                )
                self.project(
                    db,
                    run_id,
                    "manifest.json",
                    payload=(encoded + "\n").encode("utf-8"),
                )
            return payload

    def completed(self, run_id: str) -> dict[str, dict]:
        with self.connect() as db:
            return {
                row["task_id"]: json.loads(row["result"])
                for row in db.execute(
                    "SELECT task_id,result FROM tasks WHERE run_id=? AND status='succeeded'",
                    (run_id,),
                )
            }

    def artifacts(self, run_id: str, task_id: str) -> list[dict]:
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM artifacts WHERE run_id=? AND task_id=?",
                    (run_id, task_id),
                )
            ]

    @staticmethod
    def assert_writable(payload: dict) -> None:
        if payload.get("metadata", {}).get("migration", {}).get("read_only"):
            raise StateConflict(
                "legacy archive is read-only; create a new run to verify its inputs"
            )

    @staticmethod
    def record_plan(db, run_id: str, data: bytes, manifest: dict) -> None:
        from kdrx.schemas.plan import ResearchPlan

        plan = ResearchPlan.model_validate_json(data)
        digest = hashlib.sha256(data).hexdigest()
        if (
            plan.plan_id != manifest["plan_id"]
            or plan.contract_id != manifest["contract_id"]
            or plan.plan_revision != manifest["metadata"]["plan"]["revision"]
            or digest != manifest["metadata"]["plan"]["sha256"]
        ):
            raise StateConflict("plan history identity/hash mismatch")
        prior = db.execute(
            "SELECT hash FROM plan_revisions WHERE run_id=? AND revision=?",
            (run_id, plan.plan_revision),
        ).fetchone()
        if prior is not None and prior[0] != digest:
            raise StateConflict("plan revision is immutable")
        db.execute(
            "INSERT OR IGNORE INTO plan_revisions VALUES(?,?,?,?)",
            (run_id, plan.plan_revision, digest, data.decode("utf-8")),
        )

    def claim(
        self,
        run_id: str,
        task_id: str,
        worker: str,
        seconds: float = 60,
        *,
        expected_revision: int | None = None,
    ) -> dict:
        if seconds <= 0:
            raise ValueError("lease duration must be positive")
        now = time.time()
        with self.transaction() as db:
            run = db.execute(
                "SELECT payload FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run:
                self.assert_writable(json.loads(run[0]))
            binding = (
                json.loads(run[0]).get("metadata", {}).get("plan", {}) if run else {}
            )
            if (
                expected_revision is not None
                and binding.get("revision") != expected_revision
            ):
                raise StateConflict("scheduler plan revision changed; reload the plan")
            row = db.execute(
                "SELECT * FROM tasks WHERE run_id=? AND task_id=?", (run_id, task_id)
            ).fetchone()
            if (
                row is None
                or row["status"] in {"succeeded", "cancelled"}
                or (row["status"] == "running" and row["lease_until"] > now)
            ):
                raise StateConflict("task unavailable or leased")
            if row["attempt_id"]:
                db.execute(
                    "UPDATE attempts SET status='expired',finished=? WHERE attempt_id=? AND status='running'",
                    (now, row["attempt_id"]),
                )
            attempt = uuid.uuid4().hex
            fence = row["fence"] + 1
            lease = {
                "run_id": run_id,
                "task_id": task_id,
                "attempt_id": attempt,
                "fence": fence,
                "worker_id": worker,
                "plan_revision": binding.get("revision"),
                "plan_hash": binding.get("sha256"),
            }
            db.execute(
                "UPDATE tasks SET status='running',fence=?,worker_id=?,attempt_id=?,lease_until=? WHERE run_id=? AND task_id=?",
                (fence, worker, attempt, now + seconds, run_id, task_id),
            )
            db.execute(
                "INSERT INTO attempts VALUES(?,?,?,?,?,?,NULL)",
                (attempt, run_id, task_id, fence, "running", now),
            )
            self.event(db, run_id, {"kind": "lease_acquired", **lease})
            return lease

    @staticmethod
    def assert_lease(db, lease: dict):
        if lease.get("plan_revision") is not None:
            run = db.execute(
                "SELECT payload FROM runs WHERE run_id=?", (lease["run_id"],)
            ).fetchone()
            binding = (
                json.loads(run[0]).get("metadata", {}).get("plan", {}) if run else {}
            )
            if (
                binding.get("revision") != lease["plan_revision"]
                or binding.get("sha256") != lease["plan_hash"]
            ):
                raise StateConflict("leased plan revision changed")
        row = db.execute(
            "SELECT * FROM tasks WHERE run_id=? AND task_id=?",
            (lease["run_id"], lease["task_id"]),
        ).fetchone()
        if (
            row is None
            or row["status"] != "running"
            or row["fence"] != lease["fence"]
            or row["attempt_id"] != lease["attempt_id"]
            or row["worker_id"] != lease["worker_id"]
            or row["lease_until"] <= time.time()
        ):
            raise StateConflict("stale or expired task lease")

    def heartbeat(self, lease: dict, seconds: float = 60) -> None:
        if seconds <= 0:
            raise ValueError("lease duration must be positive")
        with self.transaction() as db:
            self.assert_lease(db, lease)
            db.execute(
                "UPDATE tasks SET lease_until=? WHERE run_id=? AND task_id=?",
                (time.time() + seconds, lease["run_id"], lease["task_id"]),
            )

    def reconcile_expired(self, run_id: str) -> int:
        """Fence expired workers, preserve attempt history and retain unknown usage."""
        now = time.time()
        with self.transaction() as db:
            expired = db.execute(
                "SELECT * FROM tasks WHERE run_id=? AND status='running' AND lease_until<=?",
                (run_id, now),
            ).fetchall()
            for row in expired:
                db.execute(
                    "UPDATE attempts SET status='expired',finished=? WHERE attempt_id=? AND status='running'",
                    (now, row["attempt_id"]),
                )
                db.execute(
                    "UPDATE tasks SET status='pending',fence=fence+1,lease_until=NULL WHERE run_id=? AND task_id=?",
                    (run_id, row["task_id"]),
                )
                reservation = db.execute(
                    "SELECT * FROM reservations WHERE reservation_id=? AND status='reserved'",
                    (f"model:{run_id}:{row['attempt_id']}",),
                ).fetchone()
                if reservation:
                    db.execute(
                        "UPDATE budgets SET reserved=reserved-?,spent=spent+? WHERE run_id=? AND dimension=?",
                        (
                            reservation["amount"],
                            reservation["amount"],
                            run_id,
                            reservation["dimension"],
                        ),
                    )
                    db.execute(
                        "UPDATE reservations SET actual=NULL,status='reconciled' WHERE reservation_id=?",
                        (reservation["reservation_id"],),
                    )
                self.event(
                    db,
                    run_id,
                    {
                        "kind": "lease_expired",
                        "task_id": row["task_id"],
                        "attempt_id": row["attempt_id"],
                        "fence": row["fence"],
                    },
                )
            return len(expired)

    def cancel_run(self, run_id: str) -> None:
        with self.transaction() as db:
            row = db.execute(
                "SELECT payload FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise StateConflict("unknown run")
            payload = json.loads(row[0])
            self.assert_writable(payload)
            db.execute(
                "UPDATE tasks SET status='cancelled',fence=fence+1,lease_until=NULL WHERE run_id=? AND status!='succeeded'",
                (run_id,),
            )
            db.execute(
                "UPDATE attempts SET status='cancelled',finished=? WHERE run_id=? AND status='running'",
                (time.time(), run_id),
            )
            payload["status"] = "cancelled"
            payload["state_revision"] += 1
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            payload["metadata"]["seal"] = {
                **payload["metadata"].get("seal", {}),
                "eligible": False,
                "revoked_reason": "run cancelled",
            }
            encoded = json.dumps(payload, ensure_ascii=False, indent=2)
            db.execute(
                "UPDATE runs SET revision=?,payload=? WHERE run_id=?",
                (payload["state_revision"], encoded, run_id),
            )
            self.project(
                db, run_id, "manifest.json", payload=(encoded + "\n").encode("utf-8")
            )
            self.event(db, run_id, {"kind": "run_cancelled"})

    def finish(
        self,
        lease: dict,
        result: dict,
        artifacts: list[dict],
        *,
        success: bool = True,
        checkpoint: dict | None = None,
        staged_events: list[dict] | None = None,
    ) -> None:
        with self.transaction() as db:
            self.assert_lease(db, lease)
            if success and (
                result.get("task_id") != lease["task_id"]
                or result.get("attempt_id") != lease["attempt_id"]
                or result.get("run_id") != lease["run_id"]
                or (
                    lease.get("plan_revision") is not None
                    and result.get("plan_revision") != lease["plan_revision"]
                )
            ):
                raise StateConflict("result execution identity mismatch")
            status = "succeeded" if success else "failed"
            if success:
                from kdrx.schemas.versioning import validate_task_output

                for artifact in artifacts:
                    validate_task_output(lease["task_id"], artifact["path"])
                    db.execute(
                        "INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?,?,?)",
                        (
                            lease["run_id"],
                            lease["task_id"],
                            artifact["path"],
                            artifact["sha256"],
                            artifact["size"],
                            lease["attempt_id"],
                        ),
                    )
                if checkpoint is not None:
                    row = db.execute(
                        "SELECT payload FROM runs WHERE run_id=?", (lease["run_id"],)
                    ).fetchone()
                    if row is None:
                        raise StateConflict("missing run checkpoint")
                    manifest = json.loads(row[0])
                    if (
                        manifest["metadata"]["plan"]["sha256"]
                        != checkpoint["plan_hash"]
                        or manifest["metadata"]["plan"]["revision"]
                        != result.get("plan_revision")
                        or manifest["plan_id"] != result.get("plan_id")
                    ):
                        raise StateConflict("result plan revision changed")
                    for path, digest in checkpoint.get("input_hashes", {}).items():
                        reference = db.execute(
                            "SELECT hash FROM file_projections WHERE run_id=? AND path=?",
                            (lease["run_id"], path),
                        ).fetchone()
                        if reference is not None and reference[0] != digest:
                            raise StateConflict(f"committed input changed: {path}")
                    receipt_path = f"tasks/{lease['task_id']}/result.json"
                    receipt = json.dumps(result, ensure_ascii=False, indent=2).encode(
                        "utf-8"
                    )
                    for artifact in artifacts:
                        self.project(
                            db,
                            lease["run_id"],
                            artifact["path"],
                            digest=artifact["sha256"],
                        )
                        manifest["artifact_hashes"][artifact["path"]] = artifact[
                            "sha256"
                        ]
                    self.project(db, lease["run_id"], receipt_path, payload=receipt)
                    manifest["artifact_hashes"][receipt_path] = hashlib.sha256(
                        receipt
                    ).hexdigest()
                    manifest["metadata"].setdefault("task_commits", {})[
                        lease["task_id"]
                    ] = {**checkpoint, "artifacts": artifacts}
                    if lease["task_id"] not in manifest["completed_tasks"]:
                        manifest["completed_tasks"].append(lease["task_id"])
                    manifest["failed_tasks"] = [
                        t for t in manifest["failed_tasks"] if t != lease["task_id"]
                    ]
                    manifest["state_revision"] += 1
                    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
                    encoded = json.dumps(manifest, ensure_ascii=False, indent=2)
                    db.execute(
                        "UPDATE runs SET revision=?,payload=? WHERE run_id=?",
                        (manifest["state_revision"], encoded, lease["run_id"]),
                    )
                    self.project(
                        db,
                        lease["run_id"],
                        "manifest.json",
                        payload=(encoded + "\n").encode("utf-8"),
                    )
                    for event in staged_events or []:
                        self.event(db, lease["run_id"], event)
            db.execute(
                "UPDATE tasks SET status=?,result=?,lease_until=NULL WHERE run_id=? AND task_id=?",
                (status, json.dumps(result), lease["run_id"], lease["task_id"]),
            )
            db.execute(
                "UPDATE attempts SET status=?,finished=? WHERE attempt_id=?",
                (status, time.time(), lease["attempt_id"]),
            )
            db.execute(
                "UPDATE resource_locks SET lease_until=0 WHERE attempt_id=?",
                (lease["attempt_id"],),
            )
            if success and checkpoint is not None:
                from kdrx.runtime.blackboard import publish_committed

                publish_committed(self, db, lease, artifacts)
            self.event(
                db,
                lease["run_id"],
                {
                    "kind": "task_committed" if success else "attempt_failed",
                    "task_id": lease["task_id"],
                    "attempt_id": lease["attempt_id"],
                    "fence": lease["fence"],
                },
            )

    def configure_budget(
        self, run_id: str, dimension: str, ceiling: float | None
    ) -> None:
        if ceiling is not None and ceiling < 0:
            raise ValueError("budget cannot be negative")
        with self.transaction() as db:
            prior = db.execute(
                "SELECT ceiling FROM budgets WHERE run_id=? AND dimension=?",
                (run_id, dimension),
            ).fetchone()
            if prior is not None and prior[0] != ceiling:
                raise StateConflict("budget ceiling is immutable for an existing run")
            db.execute(
                "INSERT INTO budgets(run_id,dimension,ceiling) VALUES(?,?,?) ON CONFLICT(run_id,dimension) DO NOTHING",
                (run_id, dimension, ceiling),
            )

    def reserve(
        self, run_id: str, dimension: str, amount: float, reservation_id: str
    ) -> bool:
        if amount <= 0:
            raise ValueError("reservation must be positive")
        with self.transaction() as db:
            prior = db.execute(
                "SELECT * FROM reservations WHERE reservation_id=?", (reservation_id,)
            ).fetchone()
            if prior:
                if (prior["run_id"], prior["dimension"], prior["amount"]) != (
                    run_id,
                    dimension,
                    amount,
                ):
                    raise StateConflict("reservation identity conflict")
                return False
            row = db.execute(
                "SELECT * FROM budgets WHERE run_id=? AND dimension=?",
                (run_id, dimension),
            ).fetchone()
            if row is None or (
                row["ceiling"] is not None
                and row["spent"] + row["reserved"] + amount > row["ceiling"]
            ):
                raise StateConflict("budget exhausted or unconfigured")
            db.execute(
                "UPDATE budgets SET reserved=reserved+? WHERE run_id=? AND dimension=?",
                (amount, run_id, dimension),
            )
            db.execute(
                "INSERT INTO reservations VALUES(?,?,?,?,NULL,'reserved')",
                (reservation_id, run_id, dimension, amount),
            )
            return True

    def reconcile(self, reservation_id: str, actual: float | None) -> None:
        if actual is not None and actual < 0:
            raise ValueError("usage cannot be negative")
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM reservations WHERE reservation_id=?", (reservation_id,)
            ).fetchone()
            if row is None:
                raise StateConflict("unknown reservation")
            if row["status"] != "reserved":
                if row["actual"] != actual:
                    raise StateConflict("usage already reconciled")
                return
            # Unknown usage retains the whole conservative reservation as spent.
            amount = actual if actual is not None else row["amount"]
            db.execute(
                "UPDATE budgets SET reserved=reserved-?,spent=spent+? WHERE run_id=? AND dimension=?",
                (row["amount"], amount, row["run_id"], row["dimension"]),
            )
            db.execute(
                "UPDATE reservations SET actual=?,status='reconciled' WHERE reservation_id=?",
                (actual, reservation_id),
            )

    def backup(self, destination: Path) -> None:
        if Path(destination).resolve() == self.path.resolve():
            raise ValueError("backup cannot overwrite its source")
        with self.connect() as db, closing(sqlite3.connect(destination)) as target:
            db.backup(target)

    def integrity_check(self) -> bool:
        with self.connect() as db:
            return db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
