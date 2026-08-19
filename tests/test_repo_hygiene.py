"""T-00-08: forbidden-path test.

Falha se material sensível ou dump de sandbox aparecer na árvore tracked.
Cobre B-01 (credenciais/material sensível no Git) e o gate do PR-00
("zero secret; nenhum .ssh/.agent-gw/HAR/dump na árvore de produto").
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

PRODUCT_PREFIXES = (
    "src/",
    "plugins/",
    "tests/",
    "docs/",
    ".claude/",
    ".github/",
    "evidence-manifest/",
)
PRODUCT_FILES = {
    "pyproject.toml",
    ".gitignore",
    ".gitattributes",
    "README.md",
    "LICENSE",
    "SECURITY.md",
    ".gitleaks.toml",
    ".secrets.baseline",
}

FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\.ssh(/|$)"), "chaves SSH"),
    (re.compile(r"^\.?agent-gw\.json$"), "credenciais do gateway"),
    (re.compile(r"\.har$", re.IGNORECASE), "captura HAR"),
    (re.compile(r"\.(pfx|p12|pem|key|ppk|kdbx)$", re.IGNORECASE), "certificado/chave"),
    (re.compile(r"^id_(rsa|ed25519)"), "chave privada SSH"),
    (re.compile(r"^\.dotnet(/|$)"), "cache/certificados .dotnet"),
    (re.compile(r"^\.local(/|$)"), "NSS DB / caches .local"),
    (re.compile(r"^\.config(/|$)"), "dotfiles .config"),
    (re.compile(r"^\.Xauthority$"), "Xauthority"),
    (re.compile(r"\.pid$"), "PID file"),
    (
        re.compile(
            r"^(s6|s6-rc|s6-rc_s6-rc-init_jLgjmf|runit|service|sshd|sudo|systemd"
            r"|dbus|mount|shm|lock|log|logs|temp|upload|user|sendsigs\.omit\.d|e2b)(/|$)"
        ),
        "dump de sandbox",
    ),
    (
        re.compile(r"^(extracted|evidence|auth|prompts|orchestrator|forensic-corpus)(/|$)"),
        "corpus forense",
    ),
    (
        re.compile(r"^(skills|pdf-viewer|\.cli-tools|\.websites-templates)(/|$)"),
        "dump de tooling",
    ),
    (
        re.compile(
            r"^(deep-research|deep-research-swarm|kimi-project"
            r"|moonbox-project-template|Plano|correcao)(/|$)"
        ),
        "material de pesquisa bruto",
    ),
]


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def is_product(path: str) -> bool:
    return path.startswith(PRODUCT_PREFIXES) or path in PRODUCT_FILES


def forbidden_reason(path: str) -> str | None:
    for pattern, label in FORBIDDEN_PATTERNS:
        if pattern.search(path):
            return label
    return None


@pytest.mark.xfail(
    strict=True,
    reason="Árvore ainda contaminada; vira XPASS após T-00-04 (split do repo) — remover o xfail então",
)
def test_tree_contains_only_product() -> None:
    """Gate do PR-00: git ls-files deve listar apenas produto."""
    non_product = [p for p in tracked_files() if not is_product(p)]
    assert not non_product, (
        f"{len(non_product)} arquivos não-produto na árvore. "
        f"Primeiros: {non_product[:20]}"
    )


@pytest.mark.xfail(
    strict=True,
    reason="Árvore ainda contaminada; vira XPASS após T-00-04 (split do repo) — remover o xfail então",
)
def test_no_forbidden_paths_in_tree() -> None:
    """B-01: nenhum path proibido (credenciais, HARs, dumps) na árvore."""
    violations = []
    for path in tracked_files():
        reason = forbidden_reason(path)
        if reason:
            violations.append(f"{path} ({reason})")
    assert not violations, (
        f"{len(violations)} paths proibidos na árvore:\n" + "\n".join(violations[:50])
    )


def test_detector_catches_planted_paths() -> None:
    """Prova do detector: paths plantados são classificados corretamente."""
    planted = [
        ".ssh/authorized_keys",
        "harprompt.har",
        ".dotnet/cert.pfx",
        "s6/container_environment/SSH_PASSWORD",
        "extracted/dump.bin",
        "skills/foo/SKILL.md",
    ]
    for path in planted:
        assert forbidden_reason(path) is not None, f"detector não pegou: {path}"
        assert not is_product(path), f"classificador produto pegou não-produto: {path}"


def test_detector_passes_on_clean_tree() -> None:
    """Prova da direção 'passa': uma árvore só-produto não gera violações."""
    clean = [
        "src/kdrx/cli.py",
        "src/kdrx/schemas/plan.py",
        "plugins/kdr-x/.claude-plugin/plugin.json",
        "tests/test_repo_hygiene.py",
        "docs/KDRX_README.md",
        ".claude/settings.json",
        ".github/workflows/ci.yml",
        "evidence-manifest/manifest.jsonl",
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "SECURITY.md",
    ]
    for path in clean:
        assert is_product(path), f"produto classificado como não-produto: {path}"
        assert forbidden_reason(path) is None, f"falso positivo no detector: {path}"
