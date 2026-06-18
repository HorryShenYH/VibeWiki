from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .git_utils import changed_files, current_branch, git_diff, git_status, is_git_repo, recent_commit
from .models import SessionPaths
from .project import ensure_workspace
from .text_utils import compact_list, fenced, markdown_bullets, slugify, utcish_timestamp


def _session_id(goal: str, session_name: str | None, now: datetime | None) -> str:
    stamp = (now or datetime.now().astimezone()).strftime("%Y%m%d-%H%M%S")
    slug_source = session_name or goal or "session"
    return f"{stamp}-{slugify(slug_source)}"


def _metadata_yaml(
    *,
    session_id: str,
    created_at: str,
    project: Path,
    git_repo: bool,
    branch: str,
    files: list[str],
    commit: str,
) -> str:
    file_lines = "\n".join(f"  - {item}" for item in files) or "  []"
    commit_block = "\n".join(f"  {line}" for line in commit.splitlines()) or "  none"
    return f"""session_id: {session_id}
created_at: {created_at}
project_root: {project}
git_repo: {str(git_repo).lower()}
branch: {branch}
changed_files:
{file_lines}
recent_commit: |
{commit_block}
"""


def render_session_md(
    *,
    goal: str,
    outcome: str,
    commands: list[str],
    tests: str,
    benchmark: str,
    notes: str,
    ai_summary: str,
    things_not_to_record: str,
    files: list[str],
    status: str,
    commit: str,
) -> str:
    return f"""# Session Record

## Goal

{goal or "Not provided."}

## Final Outcome

{outcome or "Not provided."}

## Key Commands

{markdown_bullets(commands)}

## Tests / Verification

{tests or "Not provided."}

## Benchmark Results

{benchmark or "Not provided."}

## Changed Files

{markdown_bullets(files)}

## Git Status

{fenced(status)}

## Recent Commit

{fenced(commit)}

## User Notes

{notes or "Not provided."}

## AI Conversation Summary

{ai_summary or "Not provided."}

## Things Not To Record

{things_not_to_record or "Not provided."}
"""


def capture_session(
    project: Path,
    *,
    goal: str = "",
    outcome: str = "",
    commands: list[str] | None = None,
    tests: str = "",
    benchmark: str = "",
    notes: str = "",
    ai_summary: str = "",
    things_not_to_record: str = "",
    session_name: str | None = None,
    now: datetime | None = None,
) -> SessionPaths:
    root = project.resolve()
    ensure_workspace(root)

    created_at = utcish_timestamp(now)
    session_id = _session_id(goal, session_name, now)
    session_dir = root / ".vibewiki" / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=False)

    git_repo = is_git_repo(root)
    branch = current_branch(root) if git_repo else "none"
    files = changed_files(root) if git_repo else []
    status = git_status(root) if git_repo else "Not a git repository."
    commit = recent_commit(root) if git_repo else "No git history."
    diff = git_diff(root) if git_repo else ""
    command_list = compact_list(commands or [])

    session_md = session_dir / "session.md"
    diff_patch = session_dir / "diff.patch"
    metadata_yaml = session_dir / "metadata.yaml"

    session_md.write_text(
        render_session_md(
            goal=goal,
            outcome=outcome,
            commands=command_list,
            tests=tests,
            benchmark=benchmark,
            notes=notes,
            ai_summary=ai_summary,
            things_not_to_record=things_not_to_record,
            files=files,
            status=status,
            commit=commit,
        ),
        encoding="utf-8",
    )
    diff_patch.write_text(diff + ("\n" if diff else ""), encoding="utf-8")
    metadata_yaml.write_text(
        _metadata_yaml(
            session_id=session_id,
            created_at=created_at,
            project=root,
            git_repo=git_repo,
            branch=branch,
            files=files,
            commit=commit,
        ),
        encoding="utf-8",
    )

    return SessionPaths(
        session_id=session_id,
        session_dir=session_dir,
        session_md=session_md,
        diff_patch=diff_patch,
        metadata_yaml=metadata_yaml,
    )

