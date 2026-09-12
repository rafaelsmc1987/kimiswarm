"""Versioned wire contracts; migration never invents verification evidence."""

from __future__ import annotations

import re
import posixpath
from pathlib import PureWindowsPath
from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict


def validate_component(value: str) -> str:
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", value)
        or value.endswith(".")
        or value.split(".")[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *[f"COM{i}" for i in range(1, 10)],
            *[f"LPT{i}" for i in range(1, 10)],
        }
    ):
        raise ValueError("identity must be a portable, opaque path component")
    return value


def normalize_artifact_path(value: str) -> str:
    """Portable relative path identity, including Windows device/stream aliases."""
    normalized = posixpath.normpath(value.replace("\\", "/"))
    if (
        normalized in {".", ".."}
        or normalized.startswith(("/", "../"))
        or PureWindowsPath(value).drive
    ):
        raise ValueError("artifact path must remain relative to its run")
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CONIN$",
        "CONOUT$",
        *[f"COM{i}" for i in range(1, 10)],
        *[f"LPT{i}" for i in range(1, 10)],
    }
    for part in normalized.split("/"):
        if (
            part.endswith((".", " "))
            or part.split(".")[0].rstrip(" .").upper() in reserved
            or any(ord(char) < 32 or char in '<>:"|?*' for char in part)
        ):
            raise ValueError(
                "artifact path contains a nonportable component or device alias"
            )
    return normalized


def validate_task_output(task_id: str, value: str) -> str:
    """Task ownership cannot include kernel control files or another task's area."""
    normalized = normalize_artifact_path(value)
    key = normalized.casefold()
    reserved = {
        "manifest.json",
        "events.jsonl",
        "plan.json",
        "plan.md",
        "request.yaml",
        "research_contract.json",
        "research_contract.yaml",
        "delivery-manifest.json",
        "dag.json",
        "waves.json",
        "planner-dispositions.json",
        "history",
        "legacy",
        "delivery/revisions",
        "verification/seal",
    }
    if any(
        key == path or key.startswith(path + "/") or path.startswith(key + "/")
        for path in reserved
    ):
        raise ValueError("task output conflicts with kernel-owned state")
    if key == "tasks" or key.startswith("tasks/"):
        parts = key.split("/")
        if (
            len(parts) < 3
            or parts[1] != task_id.casefold()
            or parts[2] == "result.json"
        ):
            raise ValueError(
                "task output conflicts with kernel receipt or another task"
            )
    return normalized


class VersionedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.3"] = "0.3"


def migrate_legacy(payload: dict) -> dict:
    """Pure v0.2 -> v0.3 migration. Keep the original for rollback."""
    result = deepcopy(payload)
    version = result.get("schema_version", "0.2")
    if version not in {"0.2", "0.2.0", "0.3"}:
        raise ValueError(f"unsupported schema version: {version}")
    result["schema_version"] = "0.3"
    return result
