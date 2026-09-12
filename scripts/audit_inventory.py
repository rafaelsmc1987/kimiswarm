"""Reproducible, read-only inventory of tracked files and packaged sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path


def inventory(root: Path) -> dict:
    names = (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
        .decode()
        .split("\0")
    )
    files, bundles = [], []
    for name in sorted(filter(None, names)):
        path = root / name
        data = path.read_bytes()
        binary = path.suffix in {".zip", ".png", ".pdf", ".whl"} or b"\0" in data
        external = name.startswith("plugins/") and not name.startswith("plugins/kdr-x/")
        kind = (
            "binary"
            if binary
            else "third-party"
            if external
            else "test"
            if name.startswith("tests/")
            else "product"
            if name.startswith(("src/", "plugins/kdr-x/"))
            else "operations"
            if name.startswith(("scripts/", ".github/"))
            else "documentation"
        )
        files.append(
            {
                "path": name,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "classification": kind,
                "manual_review_required": binary or external,
            }
        )
        if path.suffix == ".zip":
            members = []
            with zipfile.ZipFile(path) as archive:
                for member in sorted(
                    archive.infolist(), key=lambda item: item.filename
                ):
                    if member.is_dir():
                        continue
                    # Never extract or execute untrusted archive members.
                    if member.file_size > 64 * 1024 * 1024:
                        members.append(
                            {
                                "path": member.filename,
                                "status": "size_limit_uninspected",
                            }
                        )
                        continue
                    payload = archive.read(member)
                    expanded = path.parent / member.filename
                    inside = expanded.resolve().is_relative_to(path.parent.resolve())
                    same = (
                        inside
                        and expanded.is_file()
                        and expanded.read_bytes() == payload
                    )
                    members.append(
                        {
                            "path": member.filename,
                            "size": len(payload),
                            "sha256": hashlib.sha256(payload).hexdigest(),
                            "expanded_match": same,
                            "license_candidate": "license" in member.filename.lower(),
                        }
                    )
            bundles.append({"path": name, "members": members})
    return {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root)
        .decode()
        .strip(),
        "files": files,
        "bundles": bundles,
        "unclassified": [],
    }


def environment() -> dict:
    import kdrx

    versions = {}
    for tool in ("node", "claude"):
        executable = shutil.which(tool)
        if executable:
            try:
                versions[tool] = (
                    subprocess.check_output([executable, "--version"], timeout=15)
                    .decode()
                    .strip()
                )
            except (OSError, subprocess.SubprocessError) as exc:
                versions[tool] = type(exc).__name__
        else:
            versions[tool] = "unavailable"
    return {
        "python": sys.version,
        "executable": sys.executable,
        "system": platform.platform(),
        "sqlite": sqlite3.sqlite_version,
        "import_origin": kdrx.__file__,
        "tools": versions,
        "dependencies": json.loads(
            subprocess.check_output(
                [sys.executable, "-m", "pip", "list", "--format=json"]
            )
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("audit/baseline.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = {
        "inventory": inventory(root),
        "environment": environment(),
        "live_execution": "not_executed",
        "provider_cost": None,
        "test_evidence": "audit/baseline-junit.xml",
        "coverage_evidence": "audit/baseline-coverage.json",
        "limitations": [
            "Archive members compared without executing third-party code.",
            "Historical CI is not a live integration result.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
