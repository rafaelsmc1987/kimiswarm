# Skills Create Edit Download Policy

> Fonte: `harprompt.har` — JSON verbatim em `assets/raw-json/mechanics/skills_create_edit_download_policy.json`

- **skills_create_edit_download_policy**:
  - **create_or_edit_skill**:
    - **required_first_step**: Read the SKILL.md file from the skill-creator-swarm skill and follow its instructions.
    - **applies_to**:
      - creating a new skill
      - editing an existing skill
      - refining a skill through swarm-style evaluation
  - **download_skill**:
    - **via_url**:
      - Download the entire parent folder containing SKILL.md, including all contents.
      - Package it as a .skill file named after the skill-name defined in SKILL.md.
      - Example name: skill-name.skill
    - **via_command_line**:
      - Download the package.
      - Copy it from the downloads folder.
      - Repackage it as a .skill file.
    - **save_location**: /mnt/agents/output/
    - **example_output**: /mnt/agents/output/skill-name.skill
  - **mandatory_output_requirement**:
    - **after_create_edit_or_download**: Append the required file reference tag to the response.
    - **tag_format**: 
    - **path_rule**: {path_to_skill} is the full path to the .skill file, typically under /mnt/agents/output/.
    - **example**: 
  - **naming_rules**:
    - **creating_new_skill**:
      - Check /app/.user/skills and /app/.agents/skills.
      - Ensure the skill name does not already exist.
      - If a naming conflict is found, rename the new skill to a concise, appropriate, and distinct name.
    - **editing_or_downloading_skill**:
      - Keep the original name unless the user explicitly asks to rename it.
  - **related_skill**:
    - **name**: skill-creator-swarm
    - **path**: /app/.agents/skills/skill-creator-swarm/SKILL.md
    - **use_for**: Creating new skills, updating existing skills, and refining skills through swarm-style evaluation, baseline comparisons, grading, and analysis.