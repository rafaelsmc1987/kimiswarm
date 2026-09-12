"""Install the actual wheel outside the checkout and verify a real local run."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(argv, cwd):
    result = subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {result.stderr[-2000:]} {result.stdout[-2000:]}"
        )
    return result.stdout


def main():
    version = json.loads(
        (ROOT / "plugins/kdr-x/.claude-plugin/plugin.json").read_text()
    )["version"]
    artifacts = []
    for first in (ROOT / "dist/build-a").glob("*"):
        if first.suffix not in {".whl", ".zip"}:
            continue
        second = ROOT / "dist/build-b" / first.name
        a, b = first.read_bytes(), second.read_bytes()
        if a != b:
            raise ValueError(f"builds differ: {first.name}")
        artifacts.append(
            {
                "path": first.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(a).hexdigest(),
                "identical_second_build": True,
            }
        )
    wheel = next((ROOT / "dist/build-a").glob(f"kdrx-{version}-*.whl"))
    with tempfile.TemporaryDirectory(prefix="kdr-installed-") as directory:
        path = Path(directory)
        run(["uv", "venv", "--python", sys.executable, str(path / "venv")], path)
        python = (
            path / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--require-hashes",
                "-r",
                str(ROOT / "requirements-dev.lock"),
            ],
            path,
        )
        run(
            ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)],
            path,
        )
        origin = json.loads(
            run(
                [
                    str(python),
                    "-I",
                    "-c",
                    "import kdrx,json,sys,sqlite3; print(json.dumps({'origin':kdrx.__file__,'version':kdrx.__version__,'python':sys.version,'sqlite':sqlite3.sqlite_version}))",
                ],
                path,
            )
        )
        if "site-packages" not in origin["origin"] or origin["version"] != version:
            raise ValueError("wheel import came from the wrong installation")
        cli = [str(python), "-I", "-m", "kdrx.cli"]
        doctor = json.loads(
            run([*cli, "doctor", "--profile", "offline", "--json"], path)
        )
        corpus = path / "corpus"
        corpus.mkdir()
        (corpus / "study.txt").write_text(
            "Latency is 5 ms under load.", encoding="utf-8"
        )
        demo = json.loads(
            run(
                [
                    *cli,
                    "demo",
                    "--corpus",
                    str(corpus),
                    "--objective",
                    "latency under load",
                    "--out",
                    str(path / "runs"),
                ],
                path,
            )
        )
        run_dir = path / "runs" / demo["run_id"]
        resume = run(
            [*cli, "resume", "--run-dir", str(run_dir), "--corpus", str(corpus)], path
        )
        seal = json.loads(
            run([*cli, "seal", "--run-dir", str(run_dir), "--json"], path)
        )
        consumer = json.loads(
            run([*cli, "verify-delivery", "--run-dir", str(run_dir)], path)
        )
        run([*cli, "resume", "--run-dir", str(run_dir), "--corpus", str(corpus)], path)
        recovered = json.loads(
            run([*cli, "recover-exports", "--run-dir", str(run_dir)], path)
        )
        retention = json.loads(
            run([*cli, "gc", "--runs-root", str(path / "runs")], path)
        )
        consumer = json.loads(
            run([*cli, "verify-delivery", "--run-dir", str(run_dir)], path)
        )
        if not recovered["exports_rebuilt"] or not retention["dry_run"]:
            raise ValueError("installed maintenance commands failed")
        patch_path = path / "repair.json"
        patch_path.write_text(
            json.dumps(
                {
                    "base_revision": 0,
                    "reason": "installed package acceptance",
                    "invalidate_tasks": ["T-SYNTHESIZE"],
                }
            ),
            encoding="utf-8",
        )
        patched = json.loads(
            run(
                [
                    *cli,
                    "patch-plan",
                    "--run-dir",
                    str(run_dir),
                    "--patch",
                    str(patch_path),
                ],
                path,
            )
        )
        if patched["plan_revision"] != 1:
            raise ValueError("installed patch command failed")
        run([*cli, "resume", "--run-dir", str(run_dir), "--corpus", str(corpus)], path)
        consumer = json.loads(
            run([*cli, "verify-delivery", "--run-dir", str(run_dir)], path)
        )
        legacy = json.loads(
            run([*cli, "legacy-status", "--source", str(run_dir)], path)
        )
        imported = json.loads(
            run(
                [
                    *cli,
                    "migrate-legacy",
                    "--source",
                    str(run_dir),
                    "--runs-root",
                    str(path / "archives"),
                ],
                path,
            )
        )
        rollback = json.loads(
            run([*cli, "legacy-status", "--source", imported["backup"]], path)
        )
        if (
            imported["snapshot_hash"] != legacy["snapshot_hash"]
            or rollback["snapshot_hash"] != legacy["snapshot_hash"]
        ):
            raise ValueError("installed legacy archive verification failed")
        if not doctor["healthy"] or not seal["sealed"] or not consumer["deliverable"]:
            raise ValueError("installed wheel acceptance failed")
        output = {
            "artifacts": artifacts,
            "installed": origin,
            "doctor_healthy": True,
            "offline_pipeline": "passed",
            "resume": "passed" if resume else "empty",
            "seal": "passed",
            "consumer_verification": "passed",
            "recover_exports": "passed",
            "resume_after_seal": "passed",
            "retention_inventory": "passed",
            "plan_patch_and_selective_resume": "passed",
            "legacy_archive_and_read_only_backup": "passed",
            "host_plugin_tested": False,
            "published": False,
            "limitations": [
                "two builds in one toolchain, not independent OS environments",
                "no provider or Kimi host calls",
            ],
        }
    (ROOT / "audit/distribution.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Installed wheel, resume, seal and consumer verification passed; both builds are byte-identical."
    )


if __name__ == "__main__":
    main()
