"""Static provenance/capability inventory. Never imports or executes plugins."""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def audit(root: Path) -> dict:
    records = []
    for plugin in sorted((root / "plugins").iterdir()):
        if not plugin.is_dir():
            continue
        files, hosts, dependencies, risks, manifests, licenses = (
            [],
            set(),
            set(),
            [],
            [],
            [],
        )
        for path in sorted(plugin.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(root).as_posix()
            data = path.read_bytes()
            files.append(
                {
                    "path": rel,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size": len(data),
                }
            )
            if "license" in path.name.lower() or "notice" in path.name.lower():
                licenses.append(rel)
            if path.name in {"plugin.json", "kimi.plugin.json"}:
                manifest = json.loads(data)
                manifests.append(
                    {
                        "path": rel,
                        "version": manifest.get("version"),
                        "author": manifest.get("author"),
                        "homepage": manifest.get("homepage"),
                        "license": manifest.get("license"),
                    }
                )
            if path.suffix not in {".py", ".js", ".md", ".json", ".toml"}:
                continue
            text = data.decode("utf-8", errors="replace")
            for url in re.findall(r"https?://[^\s\"'<>]+", text):
                try:
                    host = urlsplit(url).hostname
                    if host:
                        hosts.add(host)
                except ValueError:
                    pass
            for name in (
                "agent_gw",
                "requests",
                "httpx",
                "pydantic",
                "claude",
                "codex",
            ):
                if name in text:
                    dependencies.add(name)
            for label, marker in [
                ("mutable_install_instruction", "['latest']"),
                ("mutable_install_instruction", 'get("latest")'),
                ("shell_execution", "shell=True"),
                ("network_download", "urlopen("),
                ("subprocess", "subprocess."),
                ("remote_gateway", "agent_gw"),
            ]:
                if marker in text:
                    risks.append(
                        {
                            "file": rel,
                            "kind": label,
                            "inspection": "static marker; not a runtime verdict",
                        }
                    )
        own = plugin.name == "kdr-x"
        records.append(
            {
                "plugin": plugin.name,
                "manifests": manifests,
                "license_files": licenses,
                "redistribution": "own package scope"
                if own
                else "not established; excluded from kdr-x build",
                "capability_state": "implemented-offline"
                if own
                else "disabled"
                if plugin.name in {"image_generation", "audio_generation"}
                else "external-unverified",
                "endpoint_hosts_observed": sorted(hosts),
                "dependency_markers": sorted(dependencies),
                "authentication": "local Claude Code or Codex login; no credentials in artifacts"
                if own
                else "provider-specific; availability not verified",
                "data_sent": "local evidence context for explicitly enabled inference"
                if own
                else "tool arguments; inspect provider contracts before enabling",
                "runtime_evidence": "local suite; see execution-status.json"
                if own
                else "none",
                "risks": risks,
                "files": files,
            }
        )
    return {
        "schema_version": "1",
        "method": "static file/manifest inspection; no plugin execution or legal determination",
        "plugins": records,
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    output = root / "audit/plugin-inventory.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(
        json.dumps(audit(root), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(output)
