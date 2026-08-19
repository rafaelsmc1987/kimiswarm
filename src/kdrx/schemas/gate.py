"""Deterministic gate decisions (plan §33 and §44)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import GateKind, GateVerdict

# Severidade por check (B-06 / T-04-07): existência, identidade, span e claim
# material são BLOCKING (falha => non-manifest delivery); sinais de qualidade
# (COI, currency stale, frase quantitativa sem suporte) são ADVISORY.
CheckSeverity = Literal["blocking", "advisory"]


class GateCheck(BaseModel):
    """One individual deterministic check inside a gate."""

    model_config = ConfigDict(extra="forbid")

    check_id: str
    description: str
    passed: bool
    details: Any | None = None
    severity: CheckSeverity = "blocking"


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

        Semântica por severidade (T-04-07): falha de check ``blocking``
        vira FAIL; só ``advisory`` falhando vira WARN; tudo passando, PASS.
        ``warn_is_pass`` é legado de compat — gates modernos devem usar
        ``severity`` nos checks, não este flag (E2E não aceita WARN como PASS).
        """
        failed = [c for c in checks if not c.passed]
        blocking_failed = [c for c in failed if c.severity == "blocking"]
        blocking_reasons = [f"{c.check_id}: {c.description}" for c in blocking_failed]
        if not failed:
            verdict = GateVerdict.PASS
        elif blocking_failed and not warn_is_pass:
            verdict = GateVerdict.FAIL
        elif blocking_failed:  # compat legado: gate histórico era não-bloqueante
            verdict = GateVerdict.WARN
        else:
            verdict = GateVerdict.WARN
        return cls(
            gate_id=gate_id,
            kind=kind,
            verdict=verdict,
            checks=checks,
            blocking_reasons=blocking_reasons,
            run_id=run_id,
        )
