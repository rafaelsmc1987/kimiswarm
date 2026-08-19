"""T-03-01..T-03-05: agent library, briefing guidance, policies por papel.

Lint de frontmatter (campos suportados pela doc oficial de sub-agents),
policy read-only enforced declarativamente, resolução de papel
(role-resolution.json cobre TODOS os AgentRole usados em TaskSpecs),
`.claude/agents` com controles fortes, e guidance no contrato do briefing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_AGENTS = REPO_ROOT / "plugins" / "kdr-x" / "agents"
PROJECT_AGENTS = REPO_ROOT / ".claude" / "agents"
PLAN_PY = REPO_ROOT / "src" / "kdrx" / "schemas" / "plan.py"

# Campos de frontmatter suportados (code.claude.com/docs/en/sub-agents).
# permissionMode/hooks/mcpServers são IGNORADOS em plugin agents.
SUPPORTED_FIELDS = {
    "name",
    "description",
    "tools",
    "disallowedTools",
    "model",
    "permissionMode",
    "maxTurns",
    "skills",
    "mcpServers",
    "hooks",
    "memory",
    "background",
    "effort",
    "isolation",
    "color",
    "initialPrompt",
}
PLUGIN_IGNORED_FIELDS = {"permissionMode", "hooks", "mcpServers"}
# Papel read-only: jamais Write/Edit/NotebookEdit em tools; disallowedTools
# explicita o deny para robustez.
READ_ONLY = {
    "explore",
    "plan",
    "reviewer",
    "verifier",
    "search",
    "evidence",
    "claims",
    "planner-council",
    "source-verifier",
    "claim-decomposer",
    "counterevidence-researcher",
    "devils-advocate",
    "kdr-plan-guard",
}
WRITERS = {"general", "coder", "writing", "final-integrity-auditor", "kdr-coder"}
# T-03-04: campos de controle exigidos por papel (declarados, não default).
REQUIRED_CONTROL_FIELDS = {
    "tools",
    "disallowedTools",
    "maxTurns",
    "effort",
    "background",
}


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    assert m, f"{path.name}: sem frontmatter"
    data: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        assert sep, f"{path.name}: linha inválida no frontmatter: {line!r}"
        data[key.strip()] = value.strip()
    return data


def _all_plugin_agents() -> list[Path]:
    return [p for p in sorted(PLUGIN_AGENTS.glob("*.md"))]


def test_base_and_specialist_roles_exist():
    # T-03-01 papéis base + T-03-02 especialistas
    expected_base = {"general", "coder", "explore", "plan", "reviewer", "verifier"}
    expected_spec = {"search", "evidence", "claims", "writing"}
    names = {p.stem for p in _all_plugin_agents()}
    missing = (expected_base | expected_spec) - names
    assert not missing, f"agentes faltando em plugins/kdr-x/agents: {sorted(missing)}"


def test_frontmatter_valid_and_only_supported_fields():
    for path in _all_plugin_agents() + sorted(PROJECT_AGENTS.glob("*.md")):
        fm = _frontmatter(path)
        assert fm.get("name"), f"{path.name}: name obrigatório"
        assert re.fullmatch(r"[a-z0-9-]+", fm["name"]), f"{path.name}: name inválido"
        assert fm.get("description"), f"{path.name}: description obrigatória"
        unknown = set(fm) - SUPPORTED_FIELDS
        assert not unknown, f"{path.name}: campos não suportados {sorted(unknown)}"
        ignored = set(fm) & PLUGIN_IGNORED_FIELDS
        if path.parent == PLUGIN_AGENTS:
            assert not ignored, (
                f"{path.name}: campos ignorados em plugin agents {sorted(ignored)}"
            )


def test_control_fields_declared_per_role():
    # T-03-04: policies por papel declaradas (tools, disallowedTools,
    # maxTurns, effort, background) — não herdadas implicitamente.
    for path in _all_plugin_agents() + sorted(PROJECT_AGENTS.glob("*.md")):
        fm = _frontmatter(path)
        missing = REQUIRED_CONTROL_FIELDS - set(fm)
        assert not missing, f"{path.name}: faltam campos de controle {sorted(missing)}"


def test_read_only_policy_enforced():
    for path in _all_plugin_agents() + sorted(PROJECT_AGENTS.glob("*.md")):
        fm = _frontmatter(path)
        name = fm["name"]
        tools = fm.get("tools", "")
        disallowed = fm.get("disallowedTools", "")
        if name in READ_ONLY:
            assert not re.search(r"\b(Write|Edit|NotebookEdit)\b", tools), (
                f"{name}: read-only com tool destrutiva"
            )
            assert "Write" in disallowed and "Edit" in disallowed, (
                f"{name}: read-only deve negar Write/Edit explicitamente"
            )
        elif name in WRITERS:
            pass  # writers podem escrever
        else:
            raise AssertionError(f"agent sem classificação read-only/writer: {name}")


def test_skill_fields_point_to_existing_skills():
    for path in _all_plugin_agents():
        fm = _frontmatter(path)
        skills = fm.get("skills", "")
        if skills:
            for skill in (s.strip() for s in skills.split(",") if s.strip()):
                assert (REPO_ROOT / "plugins" / "kdr-x" / "skills" / skill).exists(), (
                    f"{path.name}: skill inexistente {skill}"
                )


def test_worktree_isolation_for_code_editors():
    for path in list(PLUGIN_AGENTS.glob("coder.md")) + list(
        PROJECT_AGENTS.glob("kdr-coder.md")
    ):
        fm = _frontmatter(path)
        assert fm.get("isolation") == "worktree", (
            f"{path.name}: editor deve rodar em worktree"
        )


def test_role_resolution_covers_all_agent_roles():
    from kdrx.schemas.enums import AgentRole

    resolution = json.loads(
        (PLUGIN_AGENTS / "role-resolution.json").read_text(encoding="utf-8")
    )
    agents = {p.stem for p in _all_plugin_agents()}
    missing_roles = [r.value for r in AgentRole if r.value not in resolution["agents"]]
    assert not missing_roles, f"roles sem agent mapeado: {missing_roles}"
    bad_targets = [a for a in resolution["agents"].values() if a not in agents]
    assert not bad_targets, (
        f"role map aponta para agents inexistentes: {sorted(set(bad_targets))}"
    )


def test_every_used_taskspec_role_resolves():
    # Gate de fase: toda TaskSpec usada no DAG real resolve para um agent.
    from kdrx.runner import _retrieval_tasks

    resolution = json.loads(
        (PLUGIN_AGENTS / "role-resolution.json").read_text(encoding="utf-8")
    )
    agents = {p.stem for p in _all_plugin_agents()}
    for task in _retrieval_tasks(1):
        target = resolution["agents"].get(task.role.value)
        assert target in agents, (
            f"{task.task_id}: role {task.role} não resolve p/ agent"
        )


def test_briefing_contains_guidance_context_mission():
    # T-03-03/audit: briefing autocontido = guidance + context + mission.
    from kdrx.scheduler import _brief_for
    from kdrx.schemas.plan import (
        AcceptanceCriteria,
        AgentBrief,
        Budget,
        RetryPolicy,
        TaskSpec,
    )
    from kdrx.schemas.enums import AgentRole, Criticality, TaskStage

    assert "guidance" in AgentBrief.model_fields
    assert "context" in AgentBrief.model_fields
    assert "mission" in AgentBrief.model_fields

    task = TaskSpec(
        task_id="T-G",
        stage=TaskStage.RETRIEVAL,
        wave=0,
        role=AgentRole.SEARCH_SPECIALIST
        if hasattr(AgentRole, "SEARCH_SPECIALIST")
        else AgentRole.WEB_EXPLORER,
        mission="m",
        guidance="como-executar",
        outputs=["o"],
        tools=["read"],
        acceptance=AcceptanceCriteria(criteria=["c"], output_schema="x"),
        retry_policy=RetryPolicy(max_retries=0),
        budget=Budget(tokens=1),
        criticality=Criticality.MEDIUM,
        owner="o",
    )
    brief = _brief_for(task)
    assert brief.guidance == "como-executar"
    assert brief.mission == "m"


def test_exported_schema_includes_guidance():
    schema = json.loads(
        (
            REPO_ROOT / "plugins" / "kdr-x" / "schemas" / "AgentBrief.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert "guidance" in schema.get(
        "properties",
        schema.get("$defs", {}).get("AgentBrief", {}).get("properties", {}),
    ) or '"guidance"' in json.dumps(schema), (
        "AgentBrief.schema.json deve exportar guidance"
    )
