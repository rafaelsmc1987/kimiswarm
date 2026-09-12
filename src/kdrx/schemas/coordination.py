"""Bounded coordination contracts. Messages never certify evidence or grant tools."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, field_validator, model_validator

from kdrx.schemas.plan import Budget
from kdrx.schemas.versioning import (
    VersionedModel,
    validate_component,
    normalize_artifact_path,
)


class CoordinationPolicy(VersionedModel):
    enabled: bool = False
    max_messages: int = Field(default=1000, ge=0, le=100000)
    max_per_minute: int = Field(default=60, ge=0, le=10000)
    max_message_bytes: int = Field(default=16384, ge=256, le=65536)
    max_pending: int = Field(default=1000, ge=1, le=100000)
    max_subscriptions: int = Field(default=128, ge=1, le=1024)
    max_delivery_attempts: int = Field(default=3, ge=1, le=20)
    retry_seconds: float = Field(default=1, ge=0, le=3600, allow_inf_nan=False)


class MessageScope(VersionedModel):
    task_id: str | None = None
    subquestion_id: str | None = None

    @field_validator("task_id", "subquestion_id")
    @classmethod
    def identity(cls, value):
        return validate_component(value) if value is not None else None

    @model_validator(mode="after")
    def scoped(self):
        if not self.task_id and not self.subquestion_id:
            raise ValueError("message needs a task or subquestion scope")
        return self


class MessageRef(VersionedModel):
    kind: Literal["source", "claim", "gap", "artifact", "task"]
    ref_id: str = Field(min_length=1, max_length=256)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    path: str | None = None
    _path = field_validator("path")(lambda v: normalize_artifact_path(v) if v else v)

    @model_validator(mode="after")
    def artifact(self):
        if self.kind == "artifact" and (not self.path or not self.sha256):
            raise ValueError("artifact reference needs a path and digest")
        return self


class Message(VersionedModel):
    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str
    plan_revision: int = Field(ge=0)
    task_id: str
    scope: MessageScope
    refs: list[MessageRef] = Field(min_length=1, max_length=32)
    _identities = field_validator("message_id", "run_id", "task_id")(validate_component)


class SourceDiscovered(Message):
    kind: Literal["SourceDiscovered"] = "SourceDiscovered"
    canonical_uri: str = Field(min_length=1, max_length=2048)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def source_reference(self):
        if not any(
            r.kind == "source" and r.sha256 == self.content_hash for r in self.refs
        ):
            raise ValueError(
                "discovery needs a source reference with the observed digest"
            )
        return self


class ClaimChanged(Message):
    kind: Literal["ClaimChanged"] = "ClaimChanged"
    claim_id: str = Field(min_length=1, max_length=256)
    state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class GapOpened(Message):
    kind: Literal["GapOpened"] = "GapOpened"
    gap_id: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=2000)


class HelpRequested(Message):
    kind: Literal["HelpRequested"] = "HelpRequested"
    helper_task_id: str
    reason: str = Field(min_length=1, max_length=2000)
    budget: Budget
    deadline: float = Field(gt=0, allow_inf_nan=False)
    _helper = field_validator("helper_task_id")(validate_component)

    @model_validator(mode="after")
    def bounded_help(self):
        if not self.reason.strip() or any(
            v is None for v in self.budget.model_dump().values()
        ):
            raise ValueError(
                "help requires a reason and explicit finite budget dimensions"
            )
        if self.scope.task_id != self.helper_task_id:
            raise ValueError("help scope must name its recipient")
        return self


class ArtifactCommitted(Message):
    kind: Literal["ArtifactCommitted"] = "ArtifactCommitted"
    attempt_id: str
    _attempt = field_validator("attempt_id")(validate_component)

    @model_validator(mode="after")
    def committed_references(self):
        if any(r.kind != "artifact" for r in self.refs):
            raise ValueError("commit notifications only accept artifact references")
        return self


CoordinationMessage = Annotated[
    SourceDiscovered | ClaimChanged | GapOpened | HelpRequested | ArtifactCommitted,
    Field(discriminator="kind"),
]
MESSAGE_ADAPTER = TypeAdapter(CoordinationMessage)
