# File Paths And References

> Fonte: `harprompt.har` — JSON verbatim em `assets/raw-json/mechanics/file_paths_and_references.json`

- **file_paths_and_references**:
  - **filesystem_roots**:
    - **read_from**: /mnt/agents/
    - **write_to**: /mnt/agents/output/
    - **session_uploads**: /mnt/agents/temp/
    - **project_uploads**: /mnt/agents/upload/
  - **skill_paths**:
    - **built_in**: /app/.agents/skills/{skill_name}/SKILL.md
    - **user**: /app/.user/skills/{skill_name}/SKILL.md
  - **plugin_paths**:
    - **plugin_root**: /app/.agents/plugins/{plugin_name}/
    - **plugin_skill_file**: /app/.agents/plugins/{plugin_name}/skills/{skill_name}/SKILL.md
    - **explicit_plugin_reference**: extensionplugin:///app/.agents/plugins/{plugin_name}
  - **path_rules**:
    - **use_absolute_paths**: True
    - **read_file_requires_absolute_path**: True
    - **write_file_requires_absolute_path**: True
    - **edit_file_requires_absolute_path**: True
    - **quote_paths_with_spaces_in_shell**: True
    - **prefer_existing_files**: True
    - **read_before_overwrite**: True
    - **do_not_create_files_unless_required**: True
  - **file_reference_tags**:
    - **general_file_tag**: 
    - **skill_file_tag**: 
    - **when_to_append**: Append the tag at the end of the response for file-generating tasks.
    - **website_exception**: Do not use KIMI_REF as the final delivery mechanism for website or webapp projects; use website_version_manager.
  - **output_rules**:
    - **file_generating_tasks_require_reference**: True
    - **plain_text_allowed_for**:
      - clarifications
      - brief answers
      - progress reports
    - **large_file_rule**: If content is large, write or append in chunks and never write more than 100000 characters at once.
    - **existing_file_rule**: If the file already exists, read it first before writing.