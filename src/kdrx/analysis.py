"""Analytical compute and reproducibility (plan §27).

The rule is: a report must never contain a calculation whose origin cannot be
reproduced. Every calculation records input hashes, a deterministic script, an
output hash and unit checks; ``reproduce`` re-runs the runner and compares.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from kdrx.state import hash_bytes, hash_file

#: A runner maps input *content strings* (not paths) to the produced output.
Runner = Callable[[dict[str, str]], str]


def hash_artifact(data: str | bytes) -> str:
    if isinstance(data, str):
        return hash_bytes(data.encode("utf-8"))
    return hash_bytes(data)


@dataclass
class Calculation:
    """One reproducible computation (plan §27)."""

    calc_id: str
    inputs: dict[str, str] = field(default_factory=dict)  # name -> content hash
    script: str = ""
    output_hash: str = ""
    unit_checks: list[str] = field(default_factory=list)
    upstream: list[str] = field(default_factory=list)  # dependent calc ids
    notes: str = ""

    def reproducible_from(self, runner: Runner) -> bool:
        """Re-run the runner on the recorded inputs and compare output hashes.

        Note: the runner must be deterministic and receive the same *content*
        the input hashes describe. This validates that the recorded output hash
        actually derives from the recorded inputs.
        """
        try:
            produced = runner(self.inputs)
            return hash_artifact(produced) == self.output_hash
        except Exception:  # noqa: BLE001 - runner boundary
            return False


@dataclass
class DataLineage:
    """Lineage of a table/figure: what data produced it and how."""

    artifact_id: str
    kind: str  # "table" | "figure"
    source_data_hashes: list[str] = field(default_factory=list)
    transform: str = ""
    produced_by: str = ""


class CalculationLedger:
    """Append-only ledger of calculations with reproducibility checking."""

    def __init__(self) -> None:
        self._calcs: dict[str, Calculation] = {}

    def add(self, calc: Calculation) -> Calculation:
        if calc.calc_id in self._calcs:
            raise ValueError(f"duplicate calculation {calc.calc_id}")
        self._calcs[calc.calc_id] = calc
        return calc

    def get(self, calc_id: str) -> Calculation:
        return self._calcs[calc_id]

    def verify_all(self, runners: dict[str, Runner]) -> list[str]:
        """Return the ids of calculations that fail to reproduce.

        ``runners`` maps calc_id -> deterministic runner for that calculation.
        """
        failures: list[str] = []
        for calc_id, calc in self._calcs.items():
            runner = runners.get(calc_id)
            if runner is None:
                failures.append(calc_id)  # no runner registered -> cannot reproduce
                continue
            if not calc.reproducible_from(runner):
                failures.append(calc_id)
        return failures

    def __len__(self) -> int:
        return len(self._calcs)


def load_input_hashes(paths: dict[str, str]) -> dict[str, str]:
    """Hash input files by name (for building a Calculation)."""
    return {name: hash_file(path) for name, path in paths.items()}
