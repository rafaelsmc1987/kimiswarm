"""Canonical application boundary for CLI and host facade requests."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Literal

from kdrx.integrations.model_cli import ModelConfig

from kdrx.schemas.versioning import VersionedModel
from kdrx.schemas.plan import PlanPatch


class KernelRequest(VersionedModel):
    operation: Literal[
        "plan", "run", "resume", "research", "verify", "status", "cancel", "patch"
    ]
    objective: str | None = None
    run_id: str | None = None
    run_dir: str | None = None
    runs_root: str = ".research/runs"
    corpus: str | None = None
    backend: Literal["offline", "codex", "claude-code"] = "offline"
    model_config_options: ModelConfig | None = None
    patch: PlanPatch | None = None


class ApplicationService:
    def __init__(self, runs_root: Path):
        self.runs_root = runs_root.absolute()

    def dispatch(self, request: KernelRequest) -> dict:
        from kdrx.application.delivery import verify_snapshot
        from kdrx.retrieval import FileCorpus
        from kdrx.runner import (
            build_contract,
            build_plan,
            execute_plan,
            prepare_run_dir,
            resume_run,
        )
        from kdrx.schemas.plan import ResearchPlan
        from kdrx.schemas.request import ResearchContract
        from kdrx.state import RunState

        if request.operation in {"plan", "research"}:
            if not request.objective or not request.objective.strip():
                raise ValueError("objective is required")
            contract = build_contract(request.objective)
            plan = build_plan(contract)
            if request.backend != "offline":
                from kdrx.application.live import add_live_tasks

                plan = add_live_tasks(plan, request.backend)
            state, manifest = prepare_run_dir(
                plan, contract, self.runs_root, request.run_id
            )
        else:
            rid = request.run_id
            if request.run_dir:
                given = Path(request.run_dir).absolute()
                if given.parent.resolve() != self.runs_root.resolve():
                    raise ValueError("run_dir is outside the configured runs root")
                if rid is not None and rid != given.name:
                    raise ValueError("run identity mismatch")
                rid = given.name
            if not rid:
                raise ValueError("run_id is required")
            state = RunState(self.runs_root, rid)
            manifest = state.load_manifest()
            plan = ResearchPlan.model_validate_json(state.read_text("plan.json"))
            contract = ResearchContract.model_validate_json(
                state.read_text("research_contract.json")
            )
        output = {
            "schema_version": "0.3",
            "run_id": state.run_id,
            "run_dir": str(state.run_dir),
            "plan_hash": manifest.metadata.get("plan", {}).get("sha256"),
            "plan_revision": plan.plan_revision,
        }
        if request.operation in {"research", "run", "resume"}:
            if not request.corpus:
                raise ValueError(
                    "file corpus required; live backend is disabled until its sandbox and provider are configured"
                )
            corpus = FileCorpus(request.corpus)
            if request.operation == "resume":
                result, _ = resume_run(
                    state, corpus, model_config=request.model_config_options
                )
            else:
                result, _ = execute_plan(
                    plan,
                    contract,
                    corpus,
                    state,
                    model_config=request.model_config_options,
                )
            output.update(
                completed_tasks=result.completed,
                failed_tasks=result.failed,
                deliverable=result.deliverable,
                blocking_reasons=result.blocking_reasons,
            )
        elif request.operation == "verify":
            output.update(verify_snapshot(state).as_dict())
        elif request.operation == "status":
            from kdrx.application.delivery import delivery_status

            output.update(delivery_status(state))
        elif request.operation == "cancel":
            state.store.cancel_run(state.run_id)
            state.flush_exports()
            output["limitation"] = (
                "leases revoked; model processes stop when heartbeat observes cancellation; trusted Python handlers may finish but cannot publish"
            )
        elif request.operation == "patch":
            from kdrx.runtime.plan_revisions import apply_patch

            if request.patch is None:
                raise ValueError("typed PlanPatch required")
            output.update(apply_patch(state, request.patch))
        if manifest.metadata.get("migration", {}).get("read_only"):
            output["status"] = manifest.status.value
            output["read_only"] = True
            return output
        receipt = uuid.uuid4().hex
        output["receipt_id"] = receipt
        output["status"] = state.load_manifest().status.value
        state.append_event(
            {
                "kind": "kernel_receipt",
                "receipt_id": receipt,
                "operation": request.operation,
                "response": output,
            }
        )
        return output


def decode_request(encoded: str) -> KernelRequest:
    if len(encoded) > 1024 * 1024:
        raise ValueError("request exceeds one MiB")
    try:
        data = base64.b64decode(encoded, validate=True)
        return KernelRequest.model_validate_json(data)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid versioned request payload") from exc
