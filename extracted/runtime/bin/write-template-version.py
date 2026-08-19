#!/usr/bin/env python3
import json
import os
import pathlib
import tempfile


def main() -> None:
    path = pathlib.Path("/opt/moonbox-project-template/version.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "template": "moonbox-project",
        "template_version": os.environ.get("MOONBOX_PROJECT_TEMPLATE_VERSION", "dev"),
        "startup_mode": "s6_envd_project_mount",
        "base_image": os.environ.get("MOONBOX_BASE_IMAGE", ""),
        "envd": True,
        "envd_port": 49983,
        "entrypoint": "/opt/moonbox-project-template/bin/start-moonbox-project-sandbox.sh",
        "project_mount_path": "runtime: KIMI_PROJECT_MOUNT_DIR or PROJECT_MOUNT_PATH",
        "project_exposed_path": "/mnt/agents",
        "project_output_dir": "runtime: KIMI_PROJECT_OUTPUT_DIR or <project_dir>/output",
        "fallback_project_mount_path": "/mnt/project-space",
        "workspace_path": "/mnt/agents",
        "kernel_server_workdir": "/mnt/agents",
        "compat_paths": [
            "/mnt/agents",
            "/mnt/agents/upload",
            "/mnt/agents/uploads",
            "/mnt/agents/output",
            "/mnt/okcomputer",
            "/mnt/kimi",
            "/workspace/project",
            "/app/.user/skills",
        ],
        "capabilities": {
            "project_workspace": True,
            "okc_reception_presets": True,
            "deep_research_skills": True,
            "skills_directory": "/app/.agents/skills",
            "ssh_user": "kimi",
        },
        "services": {
            "s6": True,
            "kasmvnc": 6080,
            "kernel_server": 8888,
            "cdp_proxy": 9223,
            "sshd": 22,
        },
    }
    fd, tmp = tempfile.mkstemp(prefix=".version.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
