"""Budgeted typed notifications; help creates an explicit, reviewed DAG revision."""

from __future__ import annotations

import hashlib
import json
import time

from kdrx.runtime.notifications import policy_for, run_binding
from kdrx.runtime.store import StateConflict
from kdrx.schemas.coordination import MESSAGE_ADAPTER, CoordinationPolicy, HelpRequested
from kdrx.schemas.plan import PlanPatch, ResearchPlan


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class Blackboard:
    def __init__(self, state):
        self.state, self.store = state, state.store

    def configure(self, policy: CoordinationPolicy):
        with self.store.transaction() as db:
            run_binding(db, self.state.run_id)
            old = db.execute(
                "SELECT payload FROM coordination_policies WHERE run_id=?",
                (self.state.run_id,),
            ).fetchone()
            if old:
                if CoordinationPolicy.model_validate_json(old[0]) != policy:
                    raise StateConflict(
                        "coordination policy is immutable; create a new run"
                    )
                return
            db.execute(
                "INSERT INTO coordination_policies VALUES(?,?)",
                (self.state.run_id, policy.model_dump_json()),
            )
            self.store.event(
                db,
                self.state.run_id,
                {
                    "kind": "coordination_configured",
                    "policy": policy.model_dump(mode="json"),
                },
            )
        self.state.flush_exports()

    def _previous(self, db, message):
        if message.run_id != self.state.run_id:
            raise StateConflict("message run mismatch")
        row = db.execute(
            "SELECT request_hash,event_id FROM coordination_messages WHERE message_id=?",
            (message.message_id,),
        ).fetchone()
        if row:
            if row["request_hash"] != digest(message.model_dump(mode="json")):
                raise StateConflict("message identity reused with different content")
            return json.loads(
                db.execute(
                    "SELECT payload FROM events WHERE event_id=?", (row["event_id"],)
                ).fetchone()[0]
            )

    def _validate(self, db, message):
        manifest = run_binding(db, self.state.run_id)
        if (
            message.run_id != self.state.run_id
            or message.plan_revision != manifest["metadata"]["plan"]["revision"]
        ):
            raise StateConflict("message run or plan revision mismatch")
        row = db.execute(
            "SELECT payload FROM plan_revisions WHERE run_id=? AND revision=?",
            (message.run_id, message.plan_revision),
        ).fetchone()
        if row is None:
            raise StateConflict("versioned plan history required for coordination")
        plan = ResearchPlan.model_validate_json(row[0])
        tasks = {t.task_id for t in plan.tasks}
        if message.task_id not in tasks or (
            message.scope.task_id and message.scope.task_id not in tasks
        ):
            raise ValueError("message task/scope not in current plan")
        policy = policy_for(db, message.run_id)
        if not policy.enabled:
            raise StateConflict("coordination disabled")
        if len(message.model_dump_json().encode("utf-8")) > policy.max_message_bytes:
            raise ValueError("message size budget exceeded")
        for ref in message.refs:
            if ref.kind == "task" and ref.ref_id not in tasks:
                raise ValueError("unresolved task reference")
            if ref.kind == "artifact":
                artifact = db.execute(
                    "SELECT * FROM artifacts WHERE run_id=? AND path=? AND hash=?",
                    (message.run_id, ref.path, ref.sha256),
                ).fetchone()
                if not artifact:
                    raise ValueError(
                        "artifact notification requires a committed reference"
                    )
                if message.kind == "ArtifactCommitted" and (
                    artifact["attempt_id"] != message.attempt_id
                    or artifact["task_id"] != message.task_id
                ):
                    raise StateConflict("artifact notification producer mismatch")
        return plan, policy

    def _publish(self, db, message, *, original=None):
        plan, policy = self._validate(db, message)
        content = message.model_dump(
            mode="json",
            exclude={"message_id", "task_id", "refs"}
            if message.kind == "SourceDiscovered"
            else {"message_id"},
        )
        semantic = digest(content)
        duplicate = db.execute(
            "SELECT event_id FROM coordination_messages WHERE run_id=? AND revision=? AND semantic_key=?",
            (message.run_id, message.plan_revision, semantic),
        ).fetchone()
        if duplicate:
            return json.loads(
                db.execute(
                    "SELECT payload FROM events WHERE event_id=?", (duplicate[0],)
                ).fetchone()[0]
            )
        count, recent = db.execute(
            "SELECT COUNT(*),COALESCE(SUM(created>?),0) FROM coordination_messages WHERE run_id=?",
            (time.time() - 60, message.run_id),
        ).fetchone()
        if count >= policy.max_messages or recent >= policy.max_per_minute:
            raise ValueError("coordination message budget exhausted")
        record = self.store.event(db, message.run_id, message.model_dump(mode="json"))
        db.execute(
            "INSERT INTO coordination_messages VALUES(?,?,?,?,?,?,?)",
            (
                message.message_id,
                message.run_id,
                message.plan_revision,
                semantic,
                digest((original or message).model_dump(mode="json")),
                record["event_id"],
                time.time(),
            ),
        )
        return record

    def publish(self, message):
        message = MESSAGE_ADAPTER.validate_python(message)
        if isinstance(message, HelpRequested):
            return self.request_help(message)
        with self.store.transaction() as db:
            result = self._previous(db, message) or self._publish(db, message)
        self.state.flush_exports()
        return result

    def request_help(self, message: HelpRequested):
        from kdrx.runtime.plan_revisions import apply_patch

        message = HelpRequested.model_validate(message)
        self.state.flush_exports()
        failure = None
        with self.store.transaction() as db:
            previous = self._previous(db, message)
            if previous:
                return previous
            plan, _ = self._validate(db, message)
            if not time.time() < message.deadline <= time.time() + 86400:
                raise ValueError("help deadline expired or exceeds one day")
            task = plan.task_by_id(message.task_id)
            dependency = sorted(set(task.dependencies) | {message.helper_task_id})
            db.execute("SAVEPOINT help_patch")
            try:
                revision = apply_patch(
                    self.state,
                    PlanPatch(
                        base_revision=message.plan_revision,
                        reason=message.reason,
                        dependencies={message.task_id: dependency},
                        required_budget=message.budget,
                    ),
                    _db=db,
                )
                committed = message.model_copy(
                    update={"plan_revision": revision["plan_revision"]}
                )
                result = self._publish(db, committed, original=message)
                db.execute("RELEASE help_patch")
            except (ValueError, OSError) as exc:
                db.execute("ROLLBACK TO help_patch")
                db.execute("RELEASE help_patch")
                # Keep a diagnostic, but no hidden edge or partially applied plan.
                self.store.event(
                    db,
                    message.run_id,
                    {
                        "kind": "help_rejected",
                        "message_id": message.message_id,
                        "task_id": message.task_id,
                        "helper_task_id": message.helper_task_id,
                        "reason": str(exc)[:2000],
                    },
                )
                failure = exc
        self.state.flush_exports()
        if failure:
            raise failure
        return result


def publish_committed(store, db, lease, artifacts):
    """Optional notifications use kernel-observed commits; queue pressure cannot retry work."""
    if not artifacts or not policy_for(db, lease["run_id"]).enabled:
        return
    from kdrx.schemas.coordination import ArtifactCommitted, MessageScope
    from kdrx.state import RunState

    state = RunState(store.path.parent, lease["run_id"])
    state._store_instance = store
    board = Blackboard(state)
    for offset in range(0, len(artifacts), 16):
        message = ArtifactCommitted(
            run_id=lease["run_id"],
            plan_revision=lease["plan_revision"],
            task_id=lease["task_id"],
            attempt_id=lease["attempt_id"],
            scope=MessageScope(subquestion_id="run"),
            refs=[
                dict(
                    kind="artifact",
                    ref_id=a["path"],
                    path=a["path"],
                    sha256=a["sha256"],
                )
                for a in artifacts[offset : offset + 16]
            ],
        )
        try:
            board._publish(db, message)
        except ValueError as exc:
            store.event(
                db,
                lease["run_id"],
                {
                    "kind": "coordination_suppressed",
                    "task_id": lease["task_id"],
                    "reason": str(exc)[:300],
                    "remaining_artifacts": len(artifacts) - offset,
                },
            )
            break
