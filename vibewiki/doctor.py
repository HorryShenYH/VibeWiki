from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .text_utils import read_text_if_exists


@dataclass(frozen=True)
class DoctorReport:
    ok: bool
    lines: list[str]
    next_steps: list[str]


def build_doctor_report(project: Path) -> DoctorReport:
    root = project.expanduser().resolve()
    workspace = root / ".vibewiki"
    sessions = _directories(workspace / "sessions")
    patches = _directories(workspace / "patches")
    reviews = sorted((workspace / "reviews").glob("*.yaml")) if (workspace / "reviews").exists() else []
    latest_session = sessions[-1] if sessions else None
    latest_patch = patches[-1] if patches else None
    latest_review = reviews[-1] if reviews else None
    approved = _has_approved_review(latest_review)
    project_brief = root / "docs" / "wiki" / "project_brief.md"

    lines = [
        "VibeWiki Doctor",
        f"Project: {root}",
        "",
        "Workspace",
        f"- .vibewiki: {_status(workspace.exists())}",
        f"- config: {_status((workspace / 'config.yaml').exists())}",
        f"- events: {_status((workspace / 'events.jsonl').exists())}",
        f"- project brief: {_status(project_brief.exists())}",
        "",
        "Memory",
        f"- sessions: {len(sessions)}",
        f"- patches: {len(patches)}",
        f"- reviews: {len(reviews)}",
    ]
    if latest_session:
        lines.append(f"- latest session: {latest_session}")
    if latest_patch:
        lines.append(f"- latest patch: {latest_patch}")
    if latest_review:
        decision = "approved" if approved else "needs review"
        lines.append(f"- latest review: {latest_review} ({decision})")

    lines.extend(
        [
            "",
            "Optional Providers",
            f"- LLM: {_provider_status('VIBEWIKI_LLM_BASE_URL', 'VIBEWIKI_LLM_API_KEY', 'OPENAI_API_KEY', 'MINIMAX_API_KEY')}",
            f"- embeddings: {_provider_status('VIBEWIKI_EMBEDDING_BASE_URL', 'VIBEWIKI_EMBEDDING_API_KEY')}",
            f"- translation: {_provider_status('VIBEWIKI_TRANSLATION_PROVIDER')}",
        ]
    )

    next_steps = _next_steps(root, workspace, project_brief, sessions, patches, latest_review, approved)
    lines.extend(["", "Suggested Next Step"])
    lines.extend(f"- {step}" for step in next_steps)
    return DoctorReport(ok=workspace.exists(), lines=lines, next_steps=next_steps)


def format_doctor_report(report: DoctorReport) -> str:
    return "\n".join(report.lines).rstrip() + "\n"


def _next_steps(
    root: Path,
    workspace: Path,
    project_brief: Path,
    sessions: list[Path],
    patches: list[Path],
    latest_review: Path | None,
    approved: bool,
) -> list[str]:
    if not workspace.exists():
        return ["vibewiki init"]
    if not project_brief.exists():
        return ["vibewiki understand --output docs/wiki/project_brief.md"]
    if not sessions:
        return [
            "vibewiki capture --goal \"...\" --outcome \"...\"",
            "or: vibewiki import-markdown <session.md>",
        ]
    if not patches:
        return ["vibewiki distill"]
    latest_patch = patches[-1]
    board = latest_patch / "review_board.html"
    if not board.exists():
        return ["vibewiki review-board", "or: vibewiki review-ui"]
    if latest_review is None:
        return [f"vibewiki review --patch-dir {_display(latest_patch, root)}", "or: vibewiki review-ui"]
    if not approved:
        return [f"vibewiki review --patch-dir {_display(latest_patch, root)} --approve"]
    return [f"vibewiki merge --patch-dir {_display(latest_patch, root)}", "then: vibewiki ask \"what changed?\""]


def _directories(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.iterdir() if item.is_dir())


def _has_approved_review(path: Path | None) -> bool:
    if path is None:
        return False
    return "decision: approved" in read_text_if_exists(path)


def _status(value: bool) -> str:
    return "ok" if value else "missing"


def _provider_status(*names: str) -> str:
    configured = [name for name in names if os.environ.get(name)]
    if configured:
        return "configured via " + ", ".join(configured)
    return "not configured"


def _display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)
