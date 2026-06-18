from __future__ import annotations

from pathlib import Path

from .text_utils import write_text_if_allowed


CONFIG_TEMPLATE = """version: 1
project_name: {project_name}
wiki_dir: docs/wiki
skills_dir: skills
skilllets_dir: skills/skilllets
prompt_patterns_dir: skills/prompt_patterns
workflows_dir: skills/workflows
agent_rule_files:
  - AGENTS.md
review:
  require_human_approval: true
distill:
  mode: local
  uncertain_by_default: true
"""

WIKI_INDEX = """# Project Wiki

This Wiki contains human-reviewed project memory generated from VibeWiki
sessions.

## Pages

- [Development Notes](development_notes.md)
- [Known Issues](known_issues.md)
"""

DEVELOPMENT_NOTES = """# Development Notes

Reviewed VibeWiki knowledge patches will be appended here.
"""

KNOWN_ISSUES = """# Known Issues

Use this page for verified recurring issues, deprecated workarounds, and
important caveats.
"""

SKILLS_INDEX = """# Skills

Reusable project procedures generated or curated from VibeWiki sessions.

## Collections

- [Skilllets](skilllets/index.md): small, composable capability units.
- [Prompt Patterns](prompt_patterns/index.md): reusable prompts and task package templates.
- [Workflows](workflows/index.md): larger procedures composed from skilllets.
"""

SKILLLETS_INDEX = """# Skilllets

Small capability units extracted from one or more sessions. A skilllet should
stay narrow enough to compose with others.
"""

PROMPT_PATTERNS_INDEX = """# Prompt Patterns

Reusable prompts, task package shapes, and agent handoff templates.
"""

WORKFLOWS_INDEX = """# Workflows

Larger procedures that compose multiple skilllets or prompt patterns.
"""

AGENTS_TEMPLATE = """# Project Agent Rules

## Before Editing

- Read relevant docs in `docs/wiki/`.
- Read relevant skilllets, prompt patterns, and workflows in `skills/`.
- Check known issues before repeating an old workaround.

## After Editing

- Run the verification commands required by the touched area.
- Keep uncertain claims out of permanent docs until a human approves them.
- Capture successful sessions with VibeWiki when useful knowledge was created.
"""


def init_project(project: Path, force: bool = False) -> list[Path]:
    root = project.resolve()
    created: list[Path] = []

    for directory in [
        root / ".vibewiki" / "sessions",
        root / ".vibewiki" / "patches",
        root / ".vibewiki" / "reviews",
        root / "docs" / "wiki",
        root / "skills",
        root / "skills" / "skilllets",
        root / "skills" / "prompt_patterns",
        root / "skills" / "workflows",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    files = {
        root / ".vibewiki" / "config.yaml": CONFIG_TEMPLATE.format(project_name=root.name),
        root / "docs" / "wiki" / "index.md": WIKI_INDEX,
        root / "docs" / "wiki" / "development_notes.md": DEVELOPMENT_NOTES,
        root / "docs" / "wiki" / "known_issues.md": KNOWN_ISSUES,
        root / "skills" / "index.md": SKILLS_INDEX,
        root / "skills" / "skilllets" / "index.md": SKILLLETS_INDEX,
        root / "skills" / "prompt_patterns" / "index.md": PROMPT_PATTERNS_INDEX,
        root / "skills" / "workflows" / "index.md": WORKFLOWS_INDEX,
        root / "AGENTS.md": AGENTS_TEMPLATE,
    }

    for path, text in files.items():
        if write_text_if_allowed(path, text, force=force):
            created.append(path)

    return created


def ensure_workspace(project: Path) -> None:
    root = project.resolve()
    required = root / ".vibewiki"
    if not required.exists():
        init_project(root)
