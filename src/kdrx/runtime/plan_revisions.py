"""Immutable plan lineage and explicit, transactional selective invalidation."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import datetime, timezone

from kdrx.dag import compile_dag
from kdrx.runtime.executors import EXECUTORS
from kdrx.runtime.store import StateConflict
from kdrx.schemas.plan import PlanPatch, ResearchPlan
from kdrx.schemas.versioning import normalize_artifact_path
from kdrx.state import hash_bytes


def task_contract(task):
    # Waves and execution status are derived; all other TaskSpec fields bind work.
    return task.model_dump(mode="json", exclude={"wave", "status"}) if task else None


def receipt_plan_matches(state, plan, result, checkpoint) -> bool:
    """Accept unchanged work from an archived revision without rewriting its receipt."""
    revision = result.get("plan_revision")
    if (
        result.get("run_id") != state.run_id
        or result.get("plan_id") != plan.plan_id
        or not isinstance(revision, int)
        or not 0 <= revision <= plan.plan_revision
    ):
        return False
    with state.store.connect() as db:
        row = db.execute(
            "SELECT hash,payload FROM plan_revisions WHERE run_id=? AND revision=?",
            (state.run_id, revision),
        ).fetchone()
    if row is None:
        # Existing 0.3 runs may predate history; only their exact current plan is usable.
        raw = state._resolve("plan.json").read_bytes()
        if revision != plan.plan_revision or hash_bytes(raw) != checkpoint.get(
            "plan_hash"
        ):
            return False
    else:
        raw = row["payload"].encode("utf-8")
        if hash_bytes(raw) != row["hash"] or row["hash"] != checkpoint.get("plan_hash"):
            return False
    origin = ResearchPlan.model_validate_json(raw)
    task_id = result.get("task_id")
    return (
        origin.plan_revision == revision
        and origin.plan_id == plan.plan_id
        and origin.contract_id == plan.contract_id
        and origin.route == plan.route
        and origin.execution_backend == plan.execution_backend
        and origin.task_by_id(task_id) is not None
        and task_contract(origin.task_by_id(task_id))
        == task_contract(plan.task_by_id(task_id))
    )


def descendants(tasks, roots):
    affected = set(roots)
    while True:
        outputs = {
            normalize_artifact_path(p).casefold()
            for t in tasks
            if t.task_id in affected
            for p in t.outputs
        }
        more = {
            t.task_id
            for t in tasks
            if set(t.dependencies) & affected
            or outputs & {normalize_artifact_path(p).casefold() for p in t.inputs}
        }
        if more <= affected:
            return affected
        affected.update(more)


def apply_patch(state, patch: PlanPatch, *, _db=None) -> dict:
    """Commit the revision, invalidation, audit history and export queue together.

    A quiescent task boundary is required. Neither this API nor a patch budget
    authorizes model spending. Corpus refresh requires a new run; invalidation
    repairs outputs from the existing committed inputs.
    """
    if _db is None:
        state.flush_exports()
    store = state.store
    with store.transaction() if _db is None else nullcontext(_db) as db:
        row = db.execute(
            "SELECT payload FROM runs WHERE run_id=?", (state.run_id,)
        ).fetchone()
        if row is None:
            raise StateConflict(
                "committed run required; migrate legacy data explicitly"
            )
        manifest = json.loads(row[0])
        store.assert_writable(manifest)
        if manifest["status"] == "cancelled":
            raise StateConflict("cancelled run cannot be patched")
        binding = manifest["metadata"]["plan"]
        if binding["revision"] != patch.base_revision:
            raise StateConflict("base revision changed; rebase the patch")
        if db.execute(
            "SELECT 1 FROM tasks WHERE run_id=? AND status='running'", (state.run_id,)
        ).fetchone():
            raise StateConflict(
                "tasks in flight; stop/reconcile workers before patching"
            )
        raw = state._resolve("plan.json").read_bytes()
        store.record_plan(db, state.run_id, raw, manifest)
        old = ResearchPlan.model_validate_json(raw)
        current = {t.task_id: t for t in old.tasks}
        removed = set(patch.remove_tasks)
        invalidated = set(patch.invalidate_tasks)
        if (
            not (
                removed
                | invalidated
                | set(patch.dependencies)
                | set(patch.task_budgets)
            )
            <= current.keys()
        ):
            raise ValueError("patch references an unknown task")
        changed = set(patch.dependencies) | set(patch.task_budgets)
        if changed & set(manifest["completed_tasks"]):
            raise ValueError(
                "completed task contracts are immutable; replace with a new task ID"
            )
        if changed & removed:
            raise ValueError("cannot edit a removed task")
        seen_ids = {tid.casefold() for tid in current}
        for history in db.execute(
            "SELECT payload FROM plan_revisions WHERE run_id=?", (state.run_id,)
        ):
            seen_ids.update(
                t["task_id"].casefold() for t in json.loads(history[0])["tasks"]
            )
        for task in patch.add_tasks:
            if task.task_id.casefold() in seen_ids:
                raise ValueError("task ID already used in immutable plan history")
            seen_ids.add(task.task_id.casefold())
        for dimension, needed in patch.required_budget.model_dump().items():
            ceiling = getattr(old.budget, dimension)
            if needed is not None and ceiling is not None and needed > ceiling:
                raise ValueError(f"patch exceeds plan budget: {dimension}")
            budget = db.execute(
                "SELECT ceiling,spent,reserved FROM budgets WHERE run_id=? AND dimension=?",
                (state.run_id, dimension),
            ).fetchone()
            if (
                needed is not None
                and budget is not None
                and budget[0] is not None
                and needed > budget[0] - budget[1] - budget[2]
            ):
                raise ValueError(f"patch exceeds remaining budget: {dimension}")
        new = old.model_copy(deep=True)
        new.plan_revision += 1
        new.tasks = [t for t in new.tasks if t.task_id not in removed] + [
            t.model_copy(deep=True) for t in patch.add_tasks
        ]
        for task in new.tasks:
            if task.task_id in patch.dependencies:
                task.dependencies = patch.dependencies[task.task_id]
            if task.task_id in patch.task_budgets:
                task.budget = patch.task_budgets[task.task_id]
        dag = compile_dag(new.tasks)
        issues = [str(i) for i in dag.issues] + EXECUTORS.issues(new)
        if issues or not new.tasks:
            raise ValueError(
                "patch plan rejected: " + "; ".join(issues or ["empty plan"])
            )
        new.waves, new.ownership = dag.waves, dag.ownership
        for wave, ids in dag.waves.items():
            for tid in ids:
                new.task_by_id(tid).wave = wave
        affected = descendants(old.tasks + new.tasks, invalidated | removed | changed)
        # A task explicitly consuming plan.json treats the whole plan as input.
        affected |= descendants(
            new.tasks,
            {
                t.task_id
                for t in new.tasks
                if "plan.json"
                in {normalize_artifact_path(p).casefold() for p in t.inputs}
            },
        )
        discarded = {
            path for tid in affected if tid in current for path in current[tid].outputs
        }
        discarded.update(f"tasks/{tid}/result.json" for tid in affected)
        observed_damage = {}
        for path, digest in manifest["artifact_hashes"].items():
            file = state._resolve(path)
            actual = hash_bytes(file.read_bytes()) if file.is_file() else None
            if actual != digest:
                observed_damage[path] = {"expected": digest, "observed": actual}
                if path not in discarded:
                    raise ValueError(
                        f"integrity mismatch outside explicit invalidation: {path}"
                    )
        history = {
            "patch": patch.model_dump(mode="json"),
            "previous_manifest": manifest,
            "invalidated_tasks": sorted(affected),
            "observed_damage": observed_damage,
            "previous_results": {
                r["task_id"]: json.loads(r["result"])
                for r in db.execute(
                    "SELECT task_id,result FROM tasks WHERE run_id=? AND result IS NOT NULL",
                    (state.run_id,),
                )
            },
        }
        # Encode before modifying manifest: history remains an exact prior checkpoint.
        history_bytes = json.dumps(history, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        history_path = f"history/plan-patches/{new.plan_revision}.json"
        store.project(db, state.run_id, history_path, payload=history_bytes)
        for tid in affected:
            if tid in current and current[tid].kind == "retrieval":
                snapshot = db.execute(
                    "SELECT hash FROM artifacts WHERE run_id=? AND task_id=? AND path='corpus/sources.jsonl'",
                    (state.run_id, tid),
                ).fetchone()
                if snapshot:
                    manifest["metadata"].setdefault("retrieval_replay", {})[tid] = (
                        snapshot[0]
                    )
            db.execute(
                "UPDATE tasks SET status=?,result=NULL,fence=fence+1,lease_until=NULL WHERE run_id=? AND task_id=?",
                ("cancelled" if tid in removed else "pending", state.run_id, tid),
            )
            db.execute(
                "DELETE FROM artifacts WHERE run_id=? AND task_id=?",
                (state.run_id, tid),
            )
            manifest["metadata"].get("task_commits", {}).pop(tid, None)
        for task in new.tasks:
            db.execute(
                "INSERT OR IGNORE INTO tasks(run_id,task_id) VALUES(?,?)",
                (state.run_id, task.task_id),
            )
        for path in discarded:
            store.project(db, state.run_id, path, payload=b"")
            manifest["artifact_hashes"].pop(path, None)
        manifest["completed_tasks"] = [
            tid for tid in manifest["completed_tasks"] if tid not in affected
        ]
        manifest["failed_tasks"] = [
            tid for tid in manifest["failed_tasks"] if tid not in affected
        ]
        manifest["status"] = "pending"
        manifest["state_revision"] += 1
        manifest["plan_revision"] = new.plan_revision
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        manifest["gate_results"] = {}
        manifest["metadata"].setdefault("seal", {}).update(
            eligible=False, reason="plan_patched"
        )
        db.execute("UPDATE deliveries SET eligible=0 WHERE run_id=?", (state.run_id,))
        plan_bytes = new.model_dump_json(indent=2).encode("utf-8")
        manifest["metadata"]["plan"] = {
            "sha256": hash_bytes(plan_bytes),
            "revision": new.plan_revision,
            "source": "plan-patch",
            "review_approved": False,
        }
        manifest["artifact_hashes"].update(
            {
                "plan.json": hash_bytes(plan_bytes),
                history_path: hash_bytes(history_bytes),
            }
        )
        store.record_plan(db, state.run_id, plan_bytes, manifest)
        store.project(db, state.run_id, "plan.json", payload=plan_bytes)
        encoded = json.dumps(manifest, ensure_ascii=False, indent=2)
        db.execute(
            "UPDATE runs SET revision=?,payload=? WHERE run_id=?",
            (manifest["state_revision"], encoded, state.run_id),
        )
        store.project(
            db, state.run_id, "manifest.json", payload=(encoded + "\n").encode("utf-8")
        )
        result = {
            "run_id": state.run_id,
            "plan_revision": new.plan_revision,
            "plan_hash": hash_bytes(plan_bytes),
            "invalidated_tasks": sorted(affected),
            "history": history_path,
        }
        store.event(
            db,
            state.run_id,
            {
                "kind": "plan_patched",
                "reason": patch.reason,
                "base_revision": patch.base_revision,
                **result,
            },
        )
    if _db is None:
        state.flush_exports()
    return result
