from __future__ import annotations

from pathlib import Path

from .registry import REGISTRY_TEMPLATE
from .text_utils import write_text_if_allowed


CONFIG_TEMPLATE = """version: 1
project_name: {project_name}
memory:
  scope: {scope}
wiki_dir: docs/wiki
skills_dir: skills
skilllets_dir: skills/skilllets
prompt_patterns_dir: skills/prompt_patterns
workflows_dir: skills/workflows
agent_rule_files:
  - AGENTS.md
language:
  mode: bilingual
  primary: zh
  secondary: en
  write_policy: keep-user-language-with-brief-bilingual-summary
review:
  require_human_approval: true
distill:
  mode: local
  uncertain_by_default: true
retrieval:
  default_scope: all
  agent_scope: approved
  search_max_items: 10
  search_snippet_chars: 500
  context_max_items: 8
  context_max_chars_per_item: 700
  ask_max_items: 8
  ask_context_chars: 8000
  format: yaml
llm:
  base_url_env: VIBEWIKI_LLM_BASE_URL
  api_key_env: VIBEWIKI_LLM_API_KEY
  model_env: VIBEWIKI_LLM_MODEL
embedding:
  enabled: auto
  cache_dir: .vibewiki/cache/embeddings
  base_url_env: VIBEWIKI_EMBEDDING_BASE_URL
  api_key_env: VIBEWIKI_EMBEDDING_API_KEY
  model_env: VIBEWIKI_EMBEDDING_MODEL
translation:
  provider_env: VIBEWIKI_TRANSLATION_PROVIDER
  base_url_env: VIBEWIKI_TRANSLATION_BASE_URL
  api_key_env: VIBEWIKI_TRANSLATION_API_KEY
  default_target: zh
  cache_dir: .vibewiki/cache/translations
"""

WIKI_INDEX = """# Project Wiki / 项目 Wiki

This Wiki contains human-reviewed project memory generated from VibeWiki
sessions.

这个 Wiki 保存由 VibeWiki 会话生成、并经过人工审核的项目记忆。

## Pages / 页面

- [Development Notes](development_notes.md)
- [Knowledge](knowledge.md)
- [Known Issues](known_issues.md)
- [Todos](todos.md)
- [Ideas](ideas.md)
- [Research Notes](research_notes.md)
- [Directions](directions.md)
"""

DEVELOPMENT_NOTES = """# Development Notes / 开发记录

Reviewed VibeWiki knowledge patches will be appended here.

经过审核的 VibeWiki 知识补丁会追加到这里。
"""

KNOWN_ISSUES = """# Known Issues / 已知问题

Use this page for verified recurring issues, deprecated workarounds, and
important caveats.

用于记录已验证的反复问题、废弃 workaround 和重要注意事项。
"""

KNOWLEDGE = """# Knowledge / 知识

Reviewed facts, explanations, and project memory that are useful but not
necessarily executable skills.

记录经过审核的事实、解释和项目记忆；它们有用，但不一定是可执行 skill。
"""

TODOS = """# Todos / 待办

Reviewed follow-up tasks, loose ends, and deferred work discovered during
sessions.

记录会话中发现、经过审核的后续任务、遗留问题和延后事项。
"""

IDEAS = """# Ideas / 想法

Reviewed ideas and sparks worth keeping even when they are not immediately
actionable.

记录值得保留的想法和灵感，即使它们暂时还不能立即执行。
"""

RESEARCH_NOTES = """# Research Notes / 研究笔记

Reviewed hypotheses, experiment notes, references, and research-oriented
observations.

记录经过审核的假设、实验笔记、参考资料和研究型观察。
"""

DIRECTIONS = """# Directions / 方向

Reviewed project or research directions that may shape future work.

记录可能影响后续工作的项目方向或研究方向。
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


def init_project(project: Path, force: bool = False, scope: str = "project") -> list[Path]:
    root = project.resolve()
    clean_scope = _scope(scope)
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
        root / ".vibewiki" / "config.yaml": CONFIG_TEMPLATE.format(
            project_name=root.name,
            scope=clean_scope,
        ),
        root / ".vibewiki" / "skill_registry.yaml": REGISTRY_TEMPLATE,
        root / "docs" / "wiki" / "index.md": _wiki_index(clean_scope),
        root / "docs" / "wiki" / "development_notes.md": DEVELOPMENT_NOTES,
        root / "docs" / "wiki" / "knowledge.md": KNOWLEDGE,
        root / "docs" / "wiki" / "known_issues.md": KNOWN_ISSUES,
        root / "docs" / "wiki" / "todos.md": TODOS,
        root / "docs" / "wiki" / "ideas.md": IDEAS,
        root / "docs" / "wiki" / "research_notes.md": RESEARCH_NOTES,
        root / "docs" / "wiki" / "directions.md": DIRECTIONS,
        root / "skills" / "index.md": SKILLS_INDEX,
        root / "skills" / "skilllets" / "index.md": SKILLLETS_INDEX,
        root / "skills" / "prompt_patterns" / "index.md": PROMPT_PATTERNS_INDEX,
        root / "skills" / "workflows" / "index.md": WORKFLOWS_INDEX,
        root / "AGENTS.md": _agents_template(clean_scope),
    }

    for path, text in files.items():
        if write_text_if_allowed(path, text, force=force):
            created.append(path)

    event_log = root / ".vibewiki" / "events.jsonl"
    if not event_log.exists():
        event_log.write_text("", encoding="utf-8")
        created.append(event_log)

    if _ensure_gitignore_cache(root):
        created.append(root / ".gitignore")

    return created


def ensure_workspace(project: Path) -> None:
    root = project.resolve()
    required = root / ".vibewiki"
    if not required.exists():
        init_project(root)
        return
    for directory in [
        root / "skills" / "skilllets",
        root / "skills" / "prompt_patterns",
        root / "skills" / "workflows",
    ]:
        directory.mkdir(parents=True, exist_ok=True)
    registry = root / ".vibewiki" / "skill_registry.yaml"
    if not registry.exists():
        registry.write_text(REGISTRY_TEMPLATE, encoding="utf-8")
    event_log = root / ".vibewiki" / "events.jsonl"
    if not event_log.exists():
        event_log.write_text("", encoding="utf-8")
    _ensure_gitignore_cache(root)
    for path, text in {
        root / "docs" / "wiki" / "knowledge.md": KNOWLEDGE,
        root / "docs" / "wiki" / "todos.md": TODOS,
        root / "docs" / "wiki" / "ideas.md": IDEAS,
        root / "docs" / "wiki" / "research_notes.md": RESEARCH_NOTES,
        root / "docs" / "wiki" / "directions.md": DIRECTIONS,
    }.items():
        write_text_if_allowed(path, text)


def _ensure_gitignore_cache(root: Path) -> bool:
    path = root / ".gitignore"
    required = (".vibewiki/cache/", ".vibewiki/inbox/", ".vibewiki/trash/")
    if path.exists():
        text = path.read_text(encoding="utf-8")
        entries = {item.strip() for item in text.splitlines()}
        missing = [line for line in required if line not in entries]
        if not missing:
            return False
        suffix = "" if not text or text.endswith("\n") else "\n"
        addition = "".join(f"{line}\n" for line in missing)
        path.write_text(f"{text}{suffix}{addition}", encoding="utf-8")
        return True
    path.write_text("".join(f"{line}\n" for line in required), encoding="utf-8")
    return True


def _scope(value: str) -> str:
    clean = value.strip().lower()
    if clean in {"personal", "project"}:
        return clean
    return "project"


def _wiki_index(scope: str) -> str:
    if scope == "personal":
        return WIKI_INDEX.replace("Project Wiki / 项目 Wiki", "Personal Wiki / 个人 Wiki").replace(
            "project memory",
            "personal memory",
        ).replace("项目记忆", "个人记忆")
    return WIKI_INDEX


def _agents_template(scope: str) -> str:
    if scope == "personal":
        return AGENTS_TEMPLATE.replace("Project Agent Rules", "Personal Agent Rules").replace(
            "project guidance",
            "personal guidance",
        )
    return AGENTS_TEMPLATE
