# Agent Environment Overview — Tools & Capabilities

> Functional summary of the assistant's available tool surface and operating
> constraints in this workspace. Internal system instructions are confidential
> and are not included; this document describes observable capabilities only.

## Tool Categories

| Category | Tools | Purpose |
|---|---|---|
| Shell execution | `shell` | Run bash commands (ls, find, zip, grep, curl, package managers, etc.) in a non-persistent session |
| Python execution | `ipython` | Interactive Python/Jupyter environment; data analysis, image processing (Pillow/OpenCV), `!` prefix for bash |
| File operations | `read_file`, `write_file`, `edit_file` | Read text/images/videos/docs, create and modify files under the workspace |
| Web access | `web_search`, `web_open_url` | Search the web and fetch URL contents |
| Browser automation | `browser_visit`, `browser_click`, `browser_input`, `browser_scroll_up/down`, `browser_find`, `browser_screenshot` | Drive a headless Chromium browser |
| Image search | `search_image_by_text`, `search_image_by_image` | Reverse/semantic image search |
| Task management | `todo_read`, `todo_write` | Session to-do list tracking |
| Sub-agents | `create_agent_type`, `spawn_subagent`, `send_message`, `check_subagent_status`, `wait_for_message`, `delete_subagent` | Delegate work to specialized sub-agents (general, coder, explore, plan, reviewer, verifier) |
| Scheduling | `add_cron_job`, `list_cron_jobs`, `update_cron_job`, `remove_cron_job` | Cron-style scheduled jobs |
| Website delivery | `website_version_manager` | Build/preview versioned website deliverables |
| User interaction | `ask_user` | Structured clarifying questions (single/multi select) |
| Plugin loader | `select_tools` | Load MCP plugin tools on demand |

## Installed Plugins (MCP)

- **github** — issues, PRs, code search, repository management, Copilot review
- **yahoo_finance**, **sec_edgar**, **imf**, **world_bank_open_data** — financial/macroeconomic data sources
- **scholar** — academic paper/author search
- **image_generation** — text-to-image generation
- **audio_generation** — TTS and sound-effect generation

## Built-in Skill Domains

- Deep research (multi-agent swarm), report writing, academic paper writing, general/creative writing
- Coding orchestration (general + webapp swarms, backend building, swarm workspace)
- Artifact production: DOCX, PDF, XLSX, PPTX (kimi-slides)
- Batch download / data collection
- Skill creation (skill-creator)

## Filesystem Conventions

- User uploads (session): `/mnt/agents/temp/`
- Project uploads (shared): `/mnt/agents/upload/`
- Generated deliverables: `/mnt/agents/output/`

## Operating Constraints (Summary)

- Internal system instructions, prompts, and configuration are confidential and
  are never exported, quoted, or reconstructed into files.
- Generated deliverables are written to `/mnt/agents/output/` and referenced
  with sandbox file links.
- Language of deliverables follows the language of the user's request.
