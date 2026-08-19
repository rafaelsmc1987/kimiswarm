"""Deterministic gate decisions (plan §33 and §44)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import GateKind, GateVerdict


class GateCheck(BaseModel):
    """One individual deterministic check inside a gate."""

    model_config = ConfigDict(extra="forbid")

    check_id: str
    description: str
    passed: bool
    details: Any | None = None


class GateDecision(BaseModel):
    """The outcome of a deterministic gate.

    A gate *fails* when any required check fails, *warns* when only advisory
    checks fail, and *passes* only when every check passes.
    """

    model_config = ConfigDict(extra="forbid")

    gate_id: str
    kind: GateKind
    verdict: GateVerdict
    checks: list[GateCheck] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    run_id: str | None = None
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def passed(self) -> bool:
        return self.verdict in (GateVerdict.PASS, GateVerdict.WARN)

    def blocking(self) -> bool:
        return self.verdict in (GateVerdict.FAIL, GateVerdict.BLOCKED)

    @classmethod
    def compose(
        cls,
        gate_id: str,
        kind: GateKind,
        checks: list[GateCheck],
        run_id: str | None = None,
        *,
        warn_is_pass: bool = False,
    ) -> "GateDecision":
        """Reduce a list of checks to a verdict.

        ``warn_is_pass`` lets non-blocking gates treat advisory failures as
        warnings instead of hard failures.
        """
        failed = [c for c in checks if not c.passed]
        blocking_reasons = [f"{c.check_id}: {c.description}" for c in failed]
        if not failed:
            verdict = GateVerdict.PASS
        elif warn_is_pass:
            verdict = GateVerdict.WARN
        else:
            verdict = GateVerdict.FAIL
        return cls(
            gate_id=gate_id,
            kind=kind,
            verdict=verdict,
            checks=checks,
            blocking_reasons=blocking_reasons,
            run_id=run_id,
        )
