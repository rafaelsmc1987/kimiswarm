"""Bounded structured inference through locally authenticated model CLIs.

These are inference adapters, not an OS sandbox for arbitrary tool execution.
No provider credentials are loaded by this module or copied into run artifacts.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["codex", "claude-code"] = "codex"
    model: str | None = None
    billing: Literal["subscription", "metered"] = "subscription"
    max_calls: int = Field(default=0, ge=0, le=1000)
    timeout_seconds: float = Field(default=120, gt=0, le=3600)
    max_cost_usd: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    max_output_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=32 * 1024 * 1024)


class ModelReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    evidence_refs: list[str]
    limitations: list[str]
    blocking_issues: list[str]


class ModelError(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}: {detail}")


def executable(provider: str) -> str:
    name = {"codex": "codex", "claude-code": "claude"}[provider]
    found = shutil.which(name)
    if found:
        return found
    # The desktop installation does not always add its CLI to PATH.
    if os.name == "nt" and provider == "codex":
        candidate = (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Programs/OpenAI/Codex/bin/codex.exe"
        )
        if candidate.is_file():
            return str(candidate)
    raise ModelError("authentication", f"{name} executable unavailable")


def provider_status(provider: str) -> dict:
    """Only status/version subcommands; never inference or credential contents."""
    try:
        binary = executable(provider)
        options = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "timeout": 15,
        }
        version = subprocess.run([binary, "--version"], **options)
        args = ["login", "status"] if provider == "codex" else ["auth", "status"]
        result = subprocess.run([binary, *args], **options)
        if provider == "codex":
            authenticated = result.returncode == 0
            subscription = "chatgpt" in (result.stdout + result.stderr).lower()
        else:
            status = json.loads(result.stdout)
            authenticated = status.get("loggedIn") is True
            subscription = (
                status.get("authMethod") in {"oauth_token", "claude.ai"}
                or status.get("apiProvider") == "firstParty"
                and status.get("subscriptionType") is not None
            )
        return {
            "provider": provider,
            "installed": True,
            "authenticated": authenticated,
            "subscription": subscription,
            "version": version.stdout.strip()[:100],
            "inference_tested": False,
        }
    except (ModelError, OSError, subprocess.SubprocessError, ValueError):
        return {
            "provider": provider,
            "installed": False,
            "authenticated": False,
            "subscription": False,
            "inference_tested": False,
        }


def command(
    config: ModelConfig, directory: Path, *, binary: str | None = None
) -> list[str]:
    binary = binary or executable(config.provider)
    schema = json.dumps(ModelReply.model_json_schema(), ensure_ascii=False)
    if config.provider == "claude-code":
        argv = [
            binary,
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
            "--json-schema",
            schema,
            "--tools",
            "",
            "--safe-mode",
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--permission-mode",
            "dontAsk",
            "--no-session-persistence",
        ]
        if config.max_cost_usd is not None:
            argv += [
                "--max-budget-usd",
                str(config.max_cost_usd / max(config.max_calls, 1)),
            ]
    else:
        schema_path = directory / "response.schema.json"
        schema_path.write_text(schema, encoding="utf-8")
        argv = [
            binary,
            "exec",
            "--json",
            "--output-schema",
            str(schema_path),
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
        ]
        for setting in [
            'approval_policy="never"',
            'web_search="disabled"',
            "features.shell_tool=false",
            "features.unified_exec=false",
            "features.multi_agent=false",
            "features.apps=false",
            "features.hooks=false",
            "features.memories=false",
            "features.goals=false",
            "mcp_servers={}",
        ]:
            argv += ["-c", setting]
        argv.append("-")
    if config.model:
        argv += ["--model", config.model]
    return argv


def _kill_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    else:
        os.killpg(process.pid, signal.SIGKILL)
    if process.poll() is None:
        process.kill()


def run_process(
    argv: list[str],
    prompt: bytes,
    directory: Path,
    config: ModelConfig,
    cancelled: threading.Event | None = None,
) -> tuple[bytes, bytes, int]:
    """Bound both streams, deadline and cancellation; prompt travels through stdin."""
    if len(prompt) > 512 * 1024:
        raise ModelError("policy", "context exceeds 512 KiB")
    env = os.environ.copy()
    # Explicit subscription mode must not accidentally select metered API auth.
    if config.billing == "subscription":
        for key in (
            "OPENAI_API_KEY",
            "CODEX_API_KEY",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
        ):
            env.pop(key, None)
    env.pop("CLAUDECODE", None)
    streams = [bytearray(), bytearray()]
    overflow = threading.Event()
    process = subprocess.Popen(
        argv,
        cwd=directory,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=os.name != "nt",
    )

    def read(pipe, target):
        try:
            while chunk := pipe.read(4096):
                if len(target) + len(chunk) > config.max_output_bytes:
                    overflow.set()
                    return
                target.extend(chunk)
        finally:
            pipe.close()

    def write():
        try:
            process.stdin.write(prompt)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    readers = [
        threading.Thread(target=read, args=(pipe, target), daemon=True)
        for pipe, target in zip((process.stdout, process.stderr), streams)
    ]
    writer = threading.Thread(target=write, daemon=True)
    for thread in [*readers, writer]:
        thread.start()
    deadline = time.monotonic() + config.timeout_seconds
    error = None
    try:
        while process.poll() is None:
            if overflow.is_set():
                error = "output_limit"
                break
            if cancelled is not None and cancelled.is_set():
                error = "cancelled"
                break
            if time.monotonic() >= deadline:
                error = "timeout"
                break
            time.sleep(0.02)
    finally:
        if error or process.poll() is None:
            _kill_tree(process)
        process.wait(timeout=10)
        for thread in readers:
            thread.join(timeout=2)
    if error or overflow.is_set():
        raise ModelError(
            error or "output_limit", "model process stopped; partial output rejected"
        )
    return bytes(streams[0]), bytes(streams[1]), process.returncode


def parse_events(provider: str, raw: bytes) -> tuple[ModelReply, dict]:
    try:
        events = [
            json.loads(line)
            for line in raw.decode("utf-8").splitlines()
            if line.strip()
        ]
        if not events or any(not isinstance(event, dict) for event in events):
            raise ValueError("invalid event stream")
        usage = None
        cost = None
        final = None
        completed = False
        for event in events:
            kind = event.get("type")
            if kind in {"error", "turn.failed"} or event.get("is_error"):
                raise ModelError("provider", "provider emitted a failure event")
            if provider == "codex":
                item = event.get("item", {})
                if (
                    kind
                    and kind.startswith("item.")
                    and item.get("type")
                    not in {"agent_message", "reasoning", "todo_list"}
                ):
                    raise ModelError(
                        "policy", "unexpected tool event in inference-only adapter"
                    )
                if kind == "item.completed" and item.get("type") == "agent_message":
                    final = item["text"]
                if kind == "turn.completed":
                    completed = True
                    usage = event.get("usage")
            else:
                content = event.get("message", {}).get("content", [])
                if any(
                    block.get("type") == "tool_use"
                    and block.get("name") != "StructuredOutput"
                    for block in content
                    if isinstance(block, dict)
                ):
                    raise ModelError(
                        "policy", "unexpected tool event in inference-only adapter"
                    )
                if kind == "result":
                    completed = event.get("subtype") == "success"
                    final = event.get("structured_output") or event.get("result")
                    usage = event.get("usage")
                    cost = event.get("total_cost_usd")
        if not completed or final is None:
            raise ValueError("missing terminal success or structured response")
        reply = ModelReply.model_validate(
            json.loads(final) if isinstance(final, str) else final
        )
        return reply, {
            "usage": usage,
            "usage_known": usage is not None,
            "cost_usd": cost,
            "event_count": len(events),
            "terminal_success": True,
        }
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ModelError(
            "parse", "invalid or incomplete structured model response"
        ) from exc


class CLIModelBackend:
    def __init__(self, config: ModelConfig, store, run_id: str):
        self.config, self.store, self.run_id = config, store, run_id
        if not config.max_calls:
            raise ModelError(
                "policy", "max_calls is zero; configure a finite authorized call budget"
            )
        status = provider_status(config.provider)
        if not status["authenticated"]:
            raise ModelError("authentication", "authenticate the selected CLI locally")
        if config.billing == "subscription" and not status["subscription"]:
            raise ModelError(
                "policy", "subscription authentication could not be established"
            )
        if config.billing == "metered" and (
            config.provider == "codex" or config.max_cost_usd is None
        ):
            raise ModelError(
                "policy",
                "metered execution requires an enforceable monetary ceiling; supported only by Claude Code",
            )
        store.configure_budget(run_id, "model_calls", config.max_calls)

    def infer(
        self, prompt: str, attempt_id: str, cancelled=None
    ) -> tuple[ModelReply, dict]:
        reservation = f"model:{self.run_id}:{attempt_id}"
        if not self.store.reserve(self.run_id, "model_calls", 1, reservation):
            raise ModelError(
                "policy", "attempt already submitted; duplicate provider call rejected"
            )
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="kdr-inference-") as directory:
                root = Path(directory)
                raw, _stderr, code = run_process(
                    command(self.config, root),
                    prompt.encode("utf-8"),
                    root,
                    self.config,
                    cancelled,
                )
                if code != 0:
                    raise ModelError(
                        "provider",
                        f"model CLI exited with status {code}; output rejected",
                    )
                reply, receipt = parse_events(self.config.provider, raw)
                receipt.update(
                    provider=self.config.provider,
                    model=self.config.model,
                    elapsed_seconds=time.monotonic() - started,
                    exit_code=code,
                    attempt_id=attempt_id,
                    billing=self.config.billing,
                )
                return reply, receipt
        finally:
            # Failed/unknown requests consumed a call as well; no automatic refund.
            self.store.reconcile(reservation, 1)
