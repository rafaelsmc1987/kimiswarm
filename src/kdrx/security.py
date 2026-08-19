"""Deterministic security controls (plan §32, §33, §10).

Retrieved content is *untrusted data*: it may never change the task, rubric,
tool permissions, source policy, output path, agent identity or gates. This
module provides the deterministic guards that enforce the boundary plus the
delivery-time security gate (secret scan, path escape, egress policy).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from kdrx.schemas.enums import GateKind
from kdrx.schemas.gate import GateCheck, GateDecision
from kdrx.verification import scan_prompt_injection


# --------------------------------------------------------------------------- #
# Path safety
# --------------------------------------------------------------------------- #
def is_within(root: str | Path, candidate: str | Path) -> bool:
    """True if ``candidate`` resolves strictly inside ``root`` (no escape)."""
    root = Path(root).resolve()
    candidate = Path(candidate).resolve()
    return candidate == root or root in candidate.parents


def safe_join(root: str | Path, *parts: str) -> Path:
    """Join and resolve, raising on any path that escapes ``root``."""
    root = Path(root).resolve()
    target = root.joinpath(*parts).resolve()
    if not is_within(root, target):
        raise ValueError(f"path escapes root: {target}")
    return target


def has_symlink_component(path: str | Path) -> bool:
    """True if any component of ``path`` is a symlink (symlink guard)."""
    path = Path(path)
    for part in path.parents:
        if part.is_symlink():
            return True
    return path.is_symlink()


def path_traversal_attempt(rel_path: str) -> bool:
    """Detect ``..`` or absolute-path markers in a relative path string."""
    return bool(rel_path.startswith("/") or re.search(r"(^|/)\.\.(/|$)", rel_path))


# --------------------------------------------------------------------------- #
# Secret scanning
# --------------------------------------------------------------------------- #
@dataclass
class SecretFinding:
    kind: str
    value_hint: str
    line: int | None = None

    def redacted(self) -> str:
        return f"{self.kind}: {self.value_hint[:8]}..."


_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "private_key",
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    ),
    (
        "github_pat",
        re.compile(r"\bghp_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    ),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai_sk", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("kimi_sk", re.compile(r"\bsk-kimi-[A-Za-z0-9_-]{20,}\b")),
    ("google_api", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
        ),
    ),
]

_SECRET_NAME_HINT = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|credential)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./=+]{16,})",
    re.IGNORECASE,
)


def scan_secrets(text: str) -> list[SecretFinding]:
    """Detect secret-like strings in ``text``.

    Conservative: it flags candidates for review; the final secret gate treats
    any hit as blocking so nothing ships with a live credential.
    """
    findings: list[SecretFinding] = []
    for kind, pat in _SECRET_PATTERNS:
        for m in pat.finditer(text):
            findings.append(SecretFinding(kind=kind, value_hint=m.group(0)))
    for m in _SECRET_NAME_HINT.finditer(text):
        findings.append(SecretFinding(kind="named_secret", value_hint=m.group(2)))
    # de-duplicate by (kind, hint)
    seen: set[tuple[str, str]] = set()
    unique: list[SecretFinding] = []
    for f in findings:
        key = (f.kind, f.value_hint)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def scan_secrets_in_file(path: str | Path) -> list[SecretFinding]:
    path = Path(path)
    if not path.exists() or not path.is_file():
        return []
    findings: list[SecretFinding] = []
    for i, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
    ):
        for f in scan_secrets(line):
            f.line = i
            findings.append(f)
    return findings


# --------------------------------------------------------------------------- #
# Egress / domain policy
# --------------------------------------------------------------------------- #
def egress_allowed(
    domain: str,
    *,
    allowlist: Iterable[str] | None = None,
    denylist: Iterable[str] | None = None,
) -> bool:
    """Decide whether a destination domain may be contacted.

    A non-empty allowlist means *only* listed domains are permitted; a denylist
    always wins regardless of the allowlist.
    """
    domain = domain.lower().strip()
    if denylist and domain in {d.lower() for d in denylist}:
        return False
    allow = {d.lower() for d in (allowlist or [])}
    if allow:
        return domain in allow or any(domain.endswith("." + d) for d in allow)
    return True


# --------------------------------------------------------------------------- #
# Instruction/data boundary
# --------------------------------------------------------------------------- #
def enforce_instruction_boundary(text: str) -> GateCheck:
    """Block imperative content in untrusted data from reaching the workflow."""
    scan = scan_prompt_injection(text)
    return GateCheck(
        check_id="INSTRUCTION_BOUNDARY",
        description="retrieved content carries no workflow-altering instructions",
        passed=not scan.suspicious,
        details=scan.markers,
    )


# --------------------------------------------------------------------------- #
# Delivery security gate
# --------------------------------------------------------------------------- #
def security_gate(
    run_dir: str | Path,
    *,
    exclude: Iterable[str] = (".git", "__pycache__"),
) -> GateDecision:
    """Delivery-time gate: secret scan + path safety over the whole run dir."""
    run_dir = Path(run_dir)
    checks: list[GateCheck] = []
    secret_findings: list[SecretFinding] = []
    path_violations: list[str] = []

    for path in run_dir.rglob("*"):
        if any(part in exclude for part in path.parts):
            continue
        if path.is_symlink():
            path_violations.append(f"symlink: {path}")
        if path.is_file():
            secret_findings.extend(scan_secrets_in_file(path))

    checks.append(
        GateCheck(
            check_id="NO_SECRETS",
            description="no live secrets in the run artifact",
            passed=not secret_findings,
            details=[f.redacted() for f in secret_findings],
        )
    )
    checks.append(
        GateCheck(
            check_id="NO_PATH_ESCAPE",
            description="no symlinks or path-escape markers in the artifact",
            passed=not path_violations,
            details=path_violations,
        )
    )
    return GateDecision.compose(
        gate_id="gate:security",
        kind=GateKind.SECURITY,
        checks=checks,
        warn_is_pass=False,
    )
