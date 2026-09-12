"""Capability claims require execution evidence, not installed directories."""

from __future__ import annotations

import importlib.util
import shutil
import sqlite3
import tempfile
from pathlib import Path

from kdrx.runtime.store import SQLiteStore, wal_supported


def capability_matrix() -> list[dict]:
    return [
        {
            "id": "file_research",
            "state": "implemented-offline",
            "backend": "python",
            "evidence": "tests/test_plan_regressions.py",
        },
        {
            "id": "http_fetch",
            "state": "external-unverified",
            "backend": "safe-http",
            "reason": "contract tests do not establish live provider availability",
        },
        {
            "id": "live_agents",
            "state": "external-unverified",
            "backends": ["claude-code", "codex"],
            "reason": "CLI adapters and five-specialist local-corpus DAG implemented; provider E2E and hostile-code OS sandbox unverified",
        },
        {
            "id": "semantic_entailment",
            "state": "planned",
            "reason": "current verifier is a deterministic lexical baseline",
        },
        {
            "id": "neural_retrieval",
            "state": "planned",
            "reason": "char-ngram retrieval is not a neural embedding",
        },
        {
            "id": "kimi_comparison",
            "state": "planned",
            "reason": "no authorized paired product evaluation recorded",
        },
        {
            "id": "image_audio",
            "state": "disabled",
            "reason": "external gateway access and redistribution rights unresolved",
        },
    ]


def doctor(
    profile: str,
    *,
    plugin_root: Path | None = None,
    probe: bool = False,
    backend: str = "codex",
) -> dict:
    import kdrx

    checks = []

    def record(name: str, passed: bool, detail: str):
        checks.append({"name": name, "passed": passed, "detail": detail})

    try:
        with tempfile.TemporaryDirectory(prefix="kdr-doctor-") as directory:
            path = Path(directory)
            store = SQLiteStore(path / "probe.sqlite3")
            store.append_event("probe", {"kind": "probe"})
            record(
                "database",
                store.integrity_check() and len(store.events("probe")) == 1,
                f"SQLite {sqlite3.sqlite_version}; journal={store.journal}; synchronous=FULL",
            )
            blob = path / "artifact.txt"
            blob.write_bytes(b"kdr-doctor")
            record(
                "artifact_roundtrip",
                blob.read_bytes() == b"kdr-doctor",
                "temporary file write/read verified",
            )
            record(
                "disk_space",
                shutil.disk_usage(path).free > 32 * 1024 * 1024,
                "requires 32 MiB free",
            )
    except (OSError, ValueError, sqlite3.Error) as exc:
        record("storage", False, str(exc))
    if profile == "plugin":
        from kdrx.cli import _check_manifest_completeness, _check_role_resolution_parity

        record(
            "plugin_root",
            plugin_root is not None,
            "set CLAUDE_PLUGIN_ROOT to installed kdr-x plugin",
        )
        if plugin_root is not None:
            problems = _check_manifest_completeness(
                plugin_root
            ) + _check_role_resolution_parity(plugin_root)
            record(
                "plugin_contract",
                not problems,
                "; ".join(problems) or "manifest and role resolution agree",
            )
        record(
            "kdr_path",
            shutil.which("kdr") is not None,
            "install the wheel in the host PATH",
        )
        host = shutil.which("claude")
        record(
            "host_installed", host is not None, "install a supported Claude Code host"
        )
        # An installed executable alone is not a host hook round-trip.
        record(
            "host_roundtrip",
            False,
            "run the protected live host acceptance suite; no verified receipt configured",
        )
    if profile == "live":
        from kdrx.integrations.model_cli import provider_status

        status = provider_status(backend)
        record(
            "provider_installed",
            status["installed"],
            f"{backend}: {status.get('version', 'unavailable')}",
        )
        record(
            "provider_authenticated",
            status["authenticated"],
            "local status only; no inference call",
        )
        record(
            "live_probe",
            False,
            "explicit provider and finite budget required; no provider call made",
        )
    return {
        "profile": profile,
        "healthy": all(item["passed"] for item in checks),
        "checks": checks,
        "version": kdrx.__version__,
        "import_origin": kdrx.__file__,
        "sqlite_version": sqlite3.sqlite_version,
        "wal_supported": wal_supported(),
        "optional_extractors": {
            name: importlib.util.find_spec(name) is not None
            for name in ("pypdf", "docx", "openpyxl")
        },
        "capabilities": capability_matrix(),
    }
