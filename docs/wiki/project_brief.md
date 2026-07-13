# Project Brief: VibeWiki

## Snapshot

- Root: repository root
- Files scanned: 71
- Skipped files: 479
- Estimated lines: 15843

## README Signal

The reviewed memory layer for AI coding agents.

## Shape

### File types

- `.md`: 40
- `.py`: 26
- `[no extension]`: 2
- `.yml`: 1
- `.toml`: 1
- `.yaml`: 1

### Top folders

- `vibewiki`: 28
- `docs`: 18
- `.`: 7
- `examples`: 5
- `.github`: 4
- `skills`: 4
- `templates`: 4
- `tests`: 1

## Orientation

### Manifests

- `pyproject.toml`

### Entrypoints

- `vibewiki/cli.py`

### Project scripts

- `vibewiki: vibewiki.cli:main`

### Docs

- `AGENTS.md`
- `CONTRIBUTING.md`
- `README.md`
- `docs/demo.md`
- `docs/design.md`
- `docs/ecosystem.md`
- `docs/improvement_backlog.md`
- `docs/mvp.md`
- `docs/research_ctx2skill.md`
- `docs/research_ecc.md`
- `docs/research_llm_wiki.md`
- `docs/roadmap.md`
- `docs/wiki/development_notes.md`
- `docs/wiki/directions.md`
- `docs/wiki/ideas.md`
- `docs/wiki/index.md`
- `docs/wiki/knowledge.md`
- `docs/wiki/known_issues.md`
- `docs/wiki/project_brief.md`
- `docs/wiki/research_notes.md`

### Tests

- `tests/test_cli_flow.py`

## Python Surface

- `tests/test_cli_flow.py:40` class `VibeWikiFlowTest`
- `vibewiki/capture.py:12` function `_session_id`
- `vibewiki/capture.py:18` function `_metadata_yaml`
- `vibewiki/capture.py:42` function `render_session_md`
- `vibewiki/capture.py:104` function `capture_session`
- `vibewiki/cli.py:31` function `_path`
- `vibewiki/cli.py:35` function `_read_text`
- `vibewiki/cli.py:41` function `_prompt`
- `vibewiki/cli.py:48` function `build_parser`
- `vibewiki/cli.py:319` function `run`
- `vibewiki/cli.py:728` function `main`
- `vibewiki/distill.py:20` class `ComposableUnitSpec`
- `vibewiki/distill.py:36` class `ComposableUnit`
- `vibewiki/distill.py:51` class `FindingSpec`
- `vibewiki/distill.py:63` class `Finding`
- `vibewiki/distill.py:503` function `latest_session_dir`
- `vibewiki/distill.py:511` function `parse_sections`
- `vibewiki/distill.py:524` function `section_has_content`
- `vibewiki/distill.py:529` function `extract_bullets`
- `vibewiki/distill.py:540` function `_clean_evidence_line`
- `vibewiki/distill.py:551` function `_keyword_matches`
- `vibewiki/distill.py:557` function `_evidence_lines`
- `vibewiki/distill.py:571` function `_detect_composable_units`
- `vibewiki/distill.py:633` function `_detect_findings`
- `vibewiki/distill.py:655` function `_looks_like_discussion_session`
- `vibewiki/distill.py:661` function `_iter_discussion_bullets`
- `vibewiki/distill.py:721` function `_iter_discussion_sections`
- `vibewiki/distill.py:777` function `_clean_discussion_text`
- `vibewiki/distill.py:785` function `_looks_like_pseudo_heading`
- `vibewiki/distill.py:817` function `_discussion_finding_kind`
- `vibewiki/distill.py:843` function `_explicit_context_kind`
- `vibewiki/distill.py:860` function `_contains_any`
- `vibewiki/distill.py:864` function `_looks_actionable_item`
- `vibewiki/distill.py:889` function `_discussion_title`
- `vibewiki/distill.py:896` function `_discussion_summary`
- `vibewiki/distill.py:901` function `_section_finding_kind`
- `vibewiki/distill.py:920` function `_discussion_findings`
- `vibewiki/distill.py:991` function `_skip_discussion_context`
- `vibewiki/distill.py:1012` function `_heuristic_findings`
- `vibewiki/distill.py:1057` function `_dedupe_findings`
- `vibewiki/distill.py:1073` function `_unit_dir_name`
- `vibewiki/distill.py:1081` function `_render_composable_unit`
- `vibewiki/distill.py:1133` function `_render_composable_index`
- `vibewiki/distill.py:1155` function `_render_finding`
- `vibewiki/distill.py:1177` function `_render_findings_index`
- `vibewiki/distill.py:1195` function `_unit_match_keywords`
- `vibewiki/distill.py:1207` function `_resolve_units_with_registry`
- `vibewiki/distill.py:1248` function `_dedupe_units`
- `vibewiki/distill.py:1265` function `_parameter_hints`
- `vibewiki/distill.py:1281` function `_questions`
- `vibewiki/distill.py:1320` function `_knowledge_patch`
- `vibewiki/distill.py:1396` function `_skill_patch`
- `vibewiki/distill.py:1482` function `_agent_rule_patch`
- `vibewiki/distill.py:1519` function `_questions_patch`
- `vibewiki/distill.py:1534` function `_write_composable_units`
- `vibewiki/distill.py:1564` function `_write_findings`
- `vibewiki/distill.py:1577` function `_clear_generated_markdown`
- `vibewiki/distill.py:1582` function `distill_session`
- `vibewiki/doctor.py:11` class `DoctorReport`
- `vibewiki/doctor.py:17` function `build_doctor_report`

### Internal imports

- `vibewiki`: 16

## First Files To Read

- `pyproject.toml`
- `vibewiki/cli.py`
- `AGENTS.md`
- `CONTRIBUTING.md`
- `README.md`
- `docs/demo.md`
- `docs/design.md`
- `docs/ecosystem.md`
- `docs/improvement_backlog.md`
- `docs/mvp.md`
- `tests/test_cli_flow.py`

## Suggested Follow-ups

- `Use this brief as the first context pack before asking an AI agent to edit the project.`
