from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

from .project import init_project
from .project_understanding import build_project_brief, render_project_brief_markdown


@dataclass(frozen=True)
class SetupResult:
    root: Path
    scope: str
    created: list[Path]
    project_brief: Path | None
    next_steps: list[str]


def run_setup_wizard(
    *,
    default_project: Path,
    scope: str = "",
    wiki_path: Path | None = None,
    project_path: Path | None = None,
    understand: bool | None = None,
    force: bool = False,
) -> SetupResult:
    selected_scope = _choice(
        "Create which kind of Wiki?",
        current=scope,
        default="project",
        choices={"project", "personal"},
    )
    if selected_scope == "personal":
        root = (
            wiki_path
            or _path_prompt(
                "Where should the personal Wiki be saved?",
                default=Path.home() / "VibeWikiPersonal",
            )
        )
        should_understand = False if understand is None else understand
    else:
        root = project_path or _path_prompt(
            "Which project should VibeWiki initialize?",
            default=default_project,
        )
        should_understand = _yes_no(
            "Generate a first project brief now?",
            current=understand,
            default=True,
        )

    root = root.expanduser().resolve()
    created = init_project(root, force=force, scope=selected_scope)
    project_brief: Path | None = None
    if should_understand:
        project_brief = root / "docs" / "wiki" / "project_brief.md"
        brief = build_project_brief(root)
        project_brief.parent.mkdir(parents=True, exist_ok=True)
        project_brief.write_text(render_project_brief_markdown(brief), encoding="utf-8")

    next_steps = _next_steps(selected_scope, project_brief is not None)
    return SetupResult(
        root=root,
        scope=selected_scope,
        created=created,
        project_brief=project_brief,
        next_steps=next_steps,
    )


def format_setup_result(result: SetupResult) -> str:
    lines = [
        "VibeWiki setup complete.",
        f"- scope: {result.scope}",
        f"- root: {result.root}",
    ]
    if result.created:
        lines.append(f"- created/refreshed files: {len(result.created)}")
    else:
        lines.append("- workspace already existed")
    if result.project_brief:
        lines.append(f"- project brief: {result.project_brief}")
    lines.append("")
    lines.append("Next steps:")
    lines.extend(f"- {step}" for step in result.next_steps)
    return "\n".join(lines).rstrip() + "\n"


def _choice(label: str, *, current: str, default: str, choices: set[str]) -> str:
    clean = current.strip().lower()
    if clean in choices:
        return clean
    if not sys.stdin.isatty():
        return default
    options = "/".join(sorted(choices))
    value = input(f"{label} [{options}] (default: {default}): ").strip().lower()
    return value if value in choices else default


def _path_prompt(label: str, *, default: Path) -> Path:
    if not sys.stdin.isatty():
        return default
    value = input(f"{label} (default: {default}): ").strip()
    return Path(value).expanduser() if value else default


def _yes_no(label: str, *, current: bool | None, default: bool) -> bool:
    if current is not None:
        return current
    if not sys.stdin.isatty():
        return default
    suffix = "Y/n" if default else "y/N"
    value = input(f"{label} [{suffix}]: ").strip().lower()
    if value in {"y", "yes"}:
        return True
    if value in {"n", "no"}:
        return False
    return default


def _next_steps(scope: str, generated_brief: bool) -> list[str]:
    if scope == "personal":
        return [
            "Import a useful AI conversation: vibewiki import-markdown <session.md>",
            "Review candidates: vibewiki distill && vibewiki review-ui",
        ]
    if generated_brief:
        return [
            "Start coding with your AI agent.",
            "After the session: vibewiki capture or vibewiki import-markdown <session.md>",
            "Then: vibewiki distill && vibewiki review-ui",
        ]
    return [
        "Generate a project brief: vibewiki understand --output docs/wiki/project_brief.md",
        "After an AI coding session: vibewiki capture or vibewiki import-markdown <session.md>",
    ]
