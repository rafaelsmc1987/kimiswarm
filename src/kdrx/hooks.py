"""Deterministic hooks (plan §33).

These are the enforceable rules that cannot depend on model goodwill. Each
hook returns a :class:`GateDecision`; the Claude Code plugin wires the same
logic into the harness (PreToolUse / Stop / SubagentStop) by shelling out to
``kdr hook <name>``, so the rules are identical in-process and in-harness.
"""

from __future__ import annotations

from typing import Any, Iterable

from kdrx.dag import CompiledDAG
from kdrx.schemas.enums import Criticality, GateKind, Standing
from kdrx.schemas.gate import GateCheck, GateDecision
from kdrx.schemas.plan import AgentResult, TaskSpec
from kdrx.schemas.artifact import DeliveryManifest

# Tool names whose *side effects* are write/destructive; read-only research
# workers must not receive them.
_WRITE_TOOLS = {"write", "edit", "notebookedit", "bash", "exec", "apply_patch"}
_READ_TOOLS = {"read", "grep", "glob", "search", "fetch", "mcp__"}

# Commands that are never allowed verbatim (plan §33).
_FORBIDDEN_COMMANDS = ("curl | sh", "curl|sh", "wget | sh", "rm -rf /", ":(){ :|:& };:")


def _check(check_id: str, description: str, passed: bool, details: object = None) -> GateCheck:
    return GateCheck(check_id=check_id, description=description, passed=passed, details=details)


def hook_task_created(task: TaskSpec) -> GateDecision:
    """Block a task that lacks mission / outputs / schema / owner / acceptance / budget."""
    checks = [
        _check("MISSION", "task has a mission", bool(task.mission.strip())),
        _check("OUTPUTS", "task declares outputs", bool(task.outputs)),
        _check("SCHEMA", "task has an output schema or acceptance criteria",
               bool(task.acceptance.output_schema or task.acceptance.criteria)),
        _check("OWNER", "task has an owner", bool(task.owner)),
        _check("BUDGET", "task budget is non-negative",
               task.budget.tokens >= 0 and task.budget.queries >= 0),
    ]
    return GateDecision.compose(f"hook:task_created:{task.task_id}", GateKind.PLAN, checks)


def hook_pre_tool_use(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    run_root: str | None = None,
    authorized_tools: Iterable[str] | None = None,
) -> GateDecision:
    """PreToolUse guards (plan §33).

    Blocks: writes outside the run/worktree, path-traversal markers, destructive
    commands, secret reads, ``curl | sh``-style command injection, and any
    unauthorized tool.
    """
    from kdrx.security import is_within, path_traversal_attempt, scan_secrets

    checks: list[GateCheck] = []
    name = tool_name.lower()

    # Unauthorized tool
    if authorized_tools is not None:
        allowed = {t.lower() for t in authorized_tools}
        checks.append(
            _check("TOOL_AUTHORIZED", f"tool '{tool_name}' is authorized", name in allowed)
        )

    # Write tool with a path -> never traverse, and stay inside run_root if given.
    if name in _WRITE_TOOLS:
        target = (
            tool_input.get("file_path")
            or tool_input.get("path")
            or tool_input.get("notebook_path")
            or tool_input.get("command")
            or ""
        )
        if isinstance(target, str) and target and path_traversal_attempt(target):
            checks.append(_check("NO_PATH_TRAVERSAL", "write target has no '..' escape", False, target))
        if run_root and isinstance(target, str) and target:
            checks.append(
                _check("WRITE_IN_SCOPE", "write target stays within the run root",
                       is_within(run_root, target), target)
            )

    # Forbidden command patterns (always applies to shell-like tools)
    command = str(tool_input.get("command", ""))
    if any(forbidden in command for forbidden in _FORBIDDEN_COMMANDS):
        checks.append(_check("NO_CMD_INJECTION", "command is not a known injection pattern", False, command))

    # Secret reads
    if name in _READ_TOOLS:
        needle = str(tool_input.get("query", "")) + " " + str(tool_input.get("pattern", ""))
        hits = scan_secrets(needle)
        checks.append(_check("NO_SECRET_READ", "read does not target a secret", not hits, [h.redacted() for h in hits]))

    if not checks:
        checks.append(_check("NOOP", "no applicable guard", True))
    return GateDecision.compose(f"hook:pre_tool_use:{tool_name}", GateKind.SECURITY, checks)


def hook_subagent_stop(result: AgentResult, task: TaskSpec) -> GateDecision:
    """SubagentStop guards (plan §33): no completion without valid output."""
    checks = [
        _check("VALID_OUTPUT", "agent produced the declared outputs",
               result.covers_outputs(task.outputs)),
        _check("EVIDENCE_REFS", "agent supplied evidence refs",
               bool(result.evidence_refs) or task.acceptance.required_evidence_refs == 0),
        _check("LIMITATIONS", "agent declared limitations", bool(result.limitations)),
        _check("TESTS_RUN", "declared tests were actually executed",
               result.tests_actually_executed()),
    ]
    return GateDecision.compose(f"hook:subagent_stop:{task.task_id}", GateKind.CLAIM, checks)


def hook_task_completed(task: TaskSpec, result: AgentResult) -> GateDecision:
    """Run the acceptance gate for a completed task (TaskCompleted hook)."""
    checks: list[GateCheck] = []
    for crit in task.acceptance.criteria:
        met = any(crit in out for out in result.outputs_produced) or crit in str(result.payload)
        checks.append(_check(f"ACCEPT:{crit}", f"acceptance criterion '{crit}'", met))
    if task.acceptance.output_schema:
        checks.append(_check("SCHEMA", "output schema declared", True))
    return GateDecision.compose(f"hook:task_completed:{task.task_id}", GateKind.PLAN, checks)


def hook_stop(
    *,
    dag: CompiledDAG,
    delivery: DeliveryManifest,
    integrity_pass: bool,
    secret_scan_clean: bool,
    artifact_open_test: bool,
    unresolved_critical: list[str],
) -> GateDecision:
    """Stop delivery gate (plan §33): no delivery without a closed, clean run."""
    checks = [
        _check("DAG_CLOSED", "DAG compiles and all nodes settled", dag.is_valid),
        _check("CRITICAL_RESOLVED", "critical claims resolved or disclosed",
               not unresolved_critical),
        _check("INTEGRITY_PASS", "final integrity gate passed", integrity_pass),
        _check("DELIVERY_MANIFEST", "delivery manifest present", bool(delivery.artifacts)),
        _check("SECRET_SCAN", "secret scan clean", secret_scan_clean),
        _check("OPEN_TEST", "artifact open test passed", artifact_open_test),
    ]
    return GateDecision.compose("hook:stop", GateKind.DELIVERY, checks)
