"""Transactional outbox, fenced delivery and an inbox for local SQL effects."""

from __future__ import annotations

import json
import time
import uuid

from kdrx.runtime.store import StateConflict
from kdrx.schemas.coordination import CoordinationPolicy
from kdrx.schemas.versioning import validate_component


def policy_for(db, run_id):
    row = db.execute(
        "SELECT payload FROM coordination_policies WHERE run_id=?", (run_id,)
    ).fetchone()
    return (
        CoordinationPolicy.model_validate_json(row[0]) if row else CoordinationPolicy()
    )


def run_binding(db, run_id):
    row = db.execute("SELECT payload FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        raise StateConflict("unknown run")
    manifest = json.loads(row[0])
    from kdrx.runtime.store import SQLiteStore

    SQLiteStore.assert_writable(manifest)
    if manifest["status"] == "cancelled":
        raise StateConflict("run cancelled")
    return manifest


def enqueue_event(db, run_id, event):
    policy = policy_for(db, run_id)
    if not policy.enabled:
        return
    for row in db.execute(
        "SELECT consumer_id,payload FROM subscriptions WHERE run_id=?", (run_id,)
    ).fetchall():
        subscription = json.loads(row["payload"])
        scope = event.get("scope", {})
        if event.get("kind") not in subscription["kinds"]:
            continue
        if scope.get("task_id") and scope["task_id"] != subscription["task_id"]:
            continue
        if (
            subscription.get("subquestion_id")
            and scope.get("subquestion_id") != subscription["subquestion_id"]
        ):
            continue
        count = db.execute(
            "SELECT COUNT(*) FROM notifications WHERE run_id=? AND consumer_id=? AND status IN ('pending','leased')",
            (run_id, row["consumer_id"]),
        ).fetchone()[0]
        # Overflow is an explicit dead letter; valid task commits are never retried for chatter.
        status = "pending" if count < policy.max_pending else "dead"
        db.execute(
            "INSERT OR IGNORE INTO notifications(run_id,consumer_id,event_id,status,last_error) VALUES(?,?,?,?,?)",
            (
                run_id,
                row["consumer_id"],
                event["event_id"],
                status,
                "queue_capacity" if status == "dead" else None,
            ),
        )


class Notifications:
    def __init__(self, store):
        self.store = store

    def subscribe(self, run_id, consumer_id, *, task_id, kinds, subquestion_id=None):
        for value in (consumer_id, task_id, subquestion_id):
            if value is not None:
                validate_component(value)
        if (
            not kinds
            or len(kinds) > 32
            or any(not isinstance(k, str) or not 1 <= len(k) <= 80 for k in kinds)
        ):
            raise ValueError("subscription requires bounded event kinds")
        payload = json.dumps(
            dict(
                task_id=task_id, kinds=sorted(set(kinds)), subquestion_id=subquestion_id
            ),
            sort_keys=True,
        )
        with self.store.transaction() as db:
            manifest = run_binding(db, run_id)
            policy = policy_for(db, run_id)
            if not policy.enabled:
                raise StateConflict("coordination disabled")
            plan = db.execute(
                "SELECT payload FROM plan_revisions WHERE run_id=? AND revision=?",
                (run_id, manifest["metadata"]["plan"]["revision"]),
            ).fetchone()
            if not plan or task_id not in {
                t["task_id"] for t in json.loads(plan[0])["tasks"]
            }:
                raise ValueError("subscription task not in current plan")
            old = db.execute(
                "SELECT payload FROM subscriptions WHERE run_id=? AND consumer_id=?",
                (run_id, consumer_id),
            ).fetchone()
            if old:
                if old[0] != payload:
                    raise StateConflict("consumer binding is immutable")
                return
            count = db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            if count >= policy.max_subscriptions:
                raise ValueError("subscription budget exhausted")
            db.execute(
                "INSERT INTO subscriptions VALUES(?,?,?)",
                (run_id, consumer_id, payload),
            )
            self.store.event(
                db,
                run_id,
                {
                    "kind": "subscription_created",
                    "consumer_id": consumer_id,
                    "task_id": task_id,
                },
            )

    def claim(self, run_id, consumer_id, worker, *, seconds=60):
        validate_component(worker)
        if not 0 < seconds <= 3600:
            raise ValueError("invalid notification lease duration")
        now = time.time()
        with self.store.transaction() as db:
            manifest = run_binding(db, run_id)
            policy = policy_for(db, run_id)
            if not policy.enabled:
                return None
            subscription = db.execute(
                "SELECT payload FROM subscriptions WHERE run_id=? AND consumer_id=?",
                (run_id, consumer_id),
            ).fetchone()
            if not subscription:
                raise StateConflict("unknown consumer")
            revision = manifest["metadata"]["plan"]["revision"]
            plan = db.execute(
                "SELECT payload FROM plan_revisions WHERE run_id=? AND revision=?",
                (run_id, revision),
            ).fetchone()
            if json.loads(subscription[0])["task_id"] not in {
                t["task_id"] for t in json.loads(plan[0])["tasks"]
            }:
                raise StateConflict("subscriber task retired from current plan")
            db.execute(
                "UPDATE notifications SET status='dead',last_error='delivery_attempts_exhausted' WHERE run_id=? AND consumer_id=? AND attempts>=? AND (status='pending' OR (status='leased' AND lease_until<=?))",
                (run_id, consumer_id, policy.max_delivery_attempts, now),
            )
            row = db.execute(
                "SELECT n.*,e.payload FROM notifications n JOIN events e ON e.event_id=n.event_id WHERE n.run_id=? AND consumer_id=? AND available_at<=? AND (status='pending' OR (status='leased' AND lease_until<=?)) ORDER BY e.seq LIMIT 1",
                (run_id, consumer_id, now, now),
            ).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            db.execute(
                "UPDATE notifications SET status='leased',attempts=attempts+1,token=?,worker_id=?,lease_until=? WHERE run_id=? AND consumer_id=? AND event_id=?",
                (token, worker, now + seconds, run_id, consumer_id, row["event_id"]),
            )
            return dict(
                run_id=run_id,
                consumer_id=consumer_id,
                event_id=row["event_id"],
                token=token,
                worker_id=worker,
                plan_revision=revision,
                event=json.loads(row["payload"]),
            )

    @staticmethod
    def _assert_delivery(db, delivery):
        row = db.execute(
            "SELECT * FROM notifications WHERE run_id=? AND consumer_id=? AND event_id=?",
            (delivery["run_id"], delivery["consumer_id"], delivery["event_id"]),
        ).fetchone()
        manifest = run_binding(db, delivery["run_id"])
        if (
            row is None
            or row["status"] != "leased"
            or row["token"] != delivery["token"]
            or row["worker_id"] != delivery["worker_id"]
            or row["lease_until"] <= time.time()
            or manifest["metadata"]["plan"]["revision"] != delivery["plan_revision"]
        ):
            raise StateConflict("stale notification lease")
        return row

    def consume(self, delivery, effect):
        """effect(db, event) must only mutate this transaction, never remote services."""
        key = (delivery["run_id"], delivery["consumer_id"], delivery["event_id"])
        try:
            with self.store.transaction() as db:
                if db.execute(
                    "SELECT 1 FROM notification_inbox WHERE run_id=? AND consumer_id=? AND event_id=?",
                    key,
                ).fetchone():
                    return False
                self._assert_delivery(db, delivery)
                # The consumer cannot substitute the payload returned by claim.
                event = json.loads(
                    db.execute(
                        "SELECT payload FROM events WHERE event_id=?",
                        (delivery["event_id"],),
                    ).fetchone()[0]
                )
                effect(db, event)
                self._assert_delivery(db, delivery)
                db.execute(
                    "INSERT INTO notification_inbox VALUES(?,?,?,?)",
                    (*key, time.time()),
                )
                db.execute(
                    "UPDATE notifications SET status='acked',lease_until=NULL WHERE run_id=? AND consumer_id=? AND event_id=?",
                    key,
                )
                return True
        except Exception as exc:
            if not isinstance(exc, StateConflict):
                self.fail(delivery, type(exc).__name__)
            raise

    def fail(self, delivery, error_code):
        with self.store.transaction() as db:
            row = self._assert_delivery(db, delivery)
            policy = policy_for(db, delivery["run_id"])
            db.execute(
                "UPDATE notifications SET status=?,lease_until=NULL,available_at=?,last_error=? WHERE run_id=? AND consumer_id=? AND event_id=?",
                (
                    "dead"
                    if row["attempts"] >= policy.max_delivery_attempts
                    else "pending",
                    time.time() + policy.retry_seconds * 2 ** (row["attempts"] - 1),
                    str(error_code)[:128],
                    delivery["run_id"],
                    delivery["consumer_id"],
                    delivery["event_id"],
                ),
            )

    def status(self, run_id):
        with self.store.connect() as db:
            return {
                r[0]: r[1]
                for r in db.execute(
                    "SELECT status,COUNT(*) FROM notifications WHERE run_id=? GROUP BY status",
                    (run_id,),
                )
            }
