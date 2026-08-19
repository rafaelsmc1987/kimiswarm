"""Persistent research artifact: exploration tree, decisions, seals (plan §31, §9).

The ARA-inspired artifact separates what was *observed* from what was
*inferred*, records decisions and dead ends, and seals every artifact with its
content hash so tampering is detectable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from kdrx.schemas.artifact import ArtifactRecord, DeliveryManifest
from kdrx.schemas.enums import ArtifactKind, SealLevel
from kdrx.state import hash_bytes, hash_file


# --------------------------------------------------------------------------- #
# Exploration tree
# --------------------------------------------------------------------------- #
@dataclass
class ExplorationNode:
    node_id: str
    kind: str  # "hypothesis" | "experiment" | "evidence" | "decision" | "dead_end"
    label: str
    parents: list[str] = field(default_factory=list)
    inferred: bool = False
    payload: dict = field(default_factory=dict)


class ExplorationTree:
    """The exploration DAG: what was explored, in what order, and why."""

    def __init__(self) -> None:
        self._nodes: dict[str, ExplorationNode] = {}

    def add(self, node: ExplorationNode) -> ExplorationNode:
        if node.node_id in self._nodes:
            raise ValueError(f"duplicate node {node.node_id}")
        self._nodes[node.node_id] = node
        return node

    def connect(self, child_id: str, parent_id: str) -> None:
        if child_id not in self._nodes or parent_id not in self._nodes:
            raise KeyError("both nodes must exist before connecting")
        if parent_id not in self._nodes[child_id].parents:
            self._nodes[child_id].parents.append(parent_id)

    def nodes(self) -> list[ExplorationNode]:
        return list(self._nodes.values())

    def observed_nodes(self) -> list[ExplorationNode]:
        """Nodes that were directly observed (not inferred) — DoD §44/§9."""
        return [n for n in self._nodes.values() if not n.inferred]

    def inferred_nodes(self) -> list[ExplorationNode]:
        return [n for n in self._nodes.values() if n.inferred]

    def to_yaml(self) -> str:
        lines = ["nodes:"]
        for n in self._nodes.values():
            lines.append(f"  - id: {n.node_id}")
            lines.append(f"    kind: {n.kind}")
            lines.append(f"    label: {n.label}")
            lines.append(f"    inferred: {str(n.inferred).lower()}")
            if n.parents:
                lines.append(f"    parents: [{', '.join(n.parents)}]")
        return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Decisions / dead ends
# --------------------------------------------------------------------------- #
@dataclass
class DecisionRecord:
    decision_id: str
    description: str
    alternatives: list[str] = field(default_factory=list)
    rationale: str = ""
    made_by: str = ""


@dataclass
class DeadEndRecord:
    dead_end_id: str
    description: str
    why_dead: str = ""


class TraceLog:
    """Append-only decision/dead-end logs (``trace/decisions.jsonl``)."""

    def __init__(self, decisions_path: str | Path, dead_ends_path: str | Path) -> None:
        self.decisions_path = Path(decisions_path)
        self.dead_ends_path = Path(dead_ends_path)
        self.decisions_path.parent.mkdir(parents=True, exist_ok=True)
        self.dead_ends_path.parent.mkdir(parents=True, exist_ok=True)

    def log_decision(self, rec: DecisionRecord) -> None:
        with self.decisions_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.__dict__, sort_keys=True) + "\n")

    def log_dead_end(self, rec: DeadEndRecord) -> None:
        with self.dead_ends_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.__dict__, sort_keys=True) + "\n")

    def iter_decisions(self) -> Iterator[dict]:
        if self.decisions_path.exists():
            for line in self.decisions_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    yield json.loads(line)


# --------------------------------------------------------------------------- #
# Seals
# --------------------------------------------------------------------------- #
def seal_artifact(record: ArtifactRecord, data: str | bytes) -> ArtifactRecord:
    """Attach a Level-1 seal: the content hash of the artifact's bytes."""
    record.content_hash = hash_artifact(data)
    record.seal_level = SealLevel.LEVEL_1_HASHED
    return record


def verify_seal(record: ArtifactRecord, path: str | Path) -> bool:
    """Re-hash the on-disk artifact and compare to the recorded hash."""
    current = hash_file(path)
    return current == record.content_hash


def hash_artifact(data: str | bytes) -> str:
    if isinstance(data, str):
        return hash_bytes(data.encode("utf-8"))
    return hash_bytes(data)


def artifact_from_file(
    artifact_id: str,
    kind: ArtifactKind,
    path: str | Path,
    produced_by: str | None = None,
) -> ArtifactRecord:
    """Create a sealed ArtifactRecord from an existing file on disk."""
    path = Path(path)
    return ArtifactRecord(
        artifact_id=artifact_id,
        kind=kind,
        path=str(path),
        content_hash=hash_file(path),
        seal_level=SealLevel.LEVEL_1_HASHED,
        produced_by=produced_by,
    )


def delivery_manifest_is_complete(manifest: DeliveryManifest) -> bool:
    return manifest.is_complete()
