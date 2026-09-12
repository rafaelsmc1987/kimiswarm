"""Ordered, expiring resource ownership tied to the runtime's task lease."""

import time
import uuid

from kdrx.runtime.store import StateConflict
from kdrx.schemas.versioning import validate_component


class ResourceLocks:
    def __init__(self, store):
        self.store = store

    def acquire(self, lease, resources, *, seconds=60):
        if not resources or len(resources) > 16 or not 0 < seconds <= 3600:
            raise ValueError("bounded resource set and duration required")
        names = sorted({validate_component(r).casefold() for r in resources})
        now = time.time()
        with self.store.transaction() as db:
            self.store.assert_lease(db, lease)
            task = db.execute(
                "SELECT lease_until FROM tasks WHERE run_id=? AND task_id=?",
                (lease["run_id"], lease["task_id"]),
            ).fetchone()
            held = {
                r[0]
                for r in db.execute(
                    "SELECT resource FROM resource_locks WHERE attempt_id=? AND lease_until>?",
                    (lease["attempt_id"], now),
                )
            }
            fresh = set(names) - held
            if held and fresh and min(fresh) < max(held):
                raise StateConflict("resource acquisition order violation")
            result = {}
            for name in names:
                row = db.execute(
                    "SELECT * FROM resource_locks WHERE resource=?", (name,)
                ).fetchone()
                if (
                    row
                    and row["lease_until"] > now
                    and row["attempt_id"] != lease["attempt_id"]
                ):
                    raise StateConflict(f"resource busy: {name}")
                token = row["token"] if name in held else uuid.uuid4().hex
                fence = (
                    row["fence"] if name in held else (row["fence"] + 1 if row else 1)
                )
                db.execute(
                    "INSERT INTO resource_locks VALUES(?,?,?,?,?,?,?) ON CONFLICT(resource) DO UPDATE SET run_id=excluded.run_id,task_id=excluded.task_id,attempt_id=excluded.attempt_id,token=excluded.token,fence=excluded.fence,lease_until=excluded.lease_until",
                    (
                        name,
                        lease["run_id"],
                        lease["task_id"],
                        lease["attempt_id"],
                        token,
                        fence,
                        min(now + seconds, task[0]),
                    ),
                )
                result[name] = dict(token=token, fence=fence)
            return result

    def check(self, lease, held):
        with self.store.transaction() as db:
            self._check(db, lease, held)

    def _check(self, db, lease, held):
        self.store.assert_lease(db, lease)
        for name, binding in held.items():
            row = db.execute(
                "SELECT * FROM resource_locks WHERE resource=?", (name,)
            ).fetchone()
            if (
                not row
                or row["attempt_id"] != lease["attempt_id"]
                or row["token"] != binding["token"]
                or row["fence"] != binding["fence"]
                or row["lease_until"] <= time.time()
            ):
                raise StateConflict("stale resource lease")

    def release(self, lease, held):
        with self.store.transaction() as db:
            self._check(db, lease, held)
            for name in held:
                db.execute(
                    "UPDATE resource_locks SET lease_until=0 WHERE resource=?", (name,)
                )
