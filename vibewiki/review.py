from __future__ import annotations

from pathlib import Path

from .distill import latest_session_dir
from .models import ReviewPaths
from .project import ensure_workspace
from .text_utils import utcish_timestamp


def latest_patch_dir(project: Path) -> Path:
    patches = sorted((project / ".vibewiki" / "patches").glob("*"))
    patches = [item for item in patches if item.is_dir()]
    if not patches:
        raise FileNotFoundError("No VibeWiki patches found. Run `vibewiki distill` first.")
    return patches[-1]


def review_patches(
    project: Path,
    *,
    patch_dir: Path | None = None,
    approve: bool = False,
    notes: str = "",
) -> ReviewPaths:
    root = project.resolve()
    ensure_workspace(root)
    selected_patch_dir = patch_dir or latest_patch_dir(root)
    session_id = selected_patch_dir.name
    review_dir = root / ".vibewiki" / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    review_file = review_dir / f"{session_id}.yaml"
    decision = "approved" if approve else "needs_review"
    review_file.write_text(
        f"""session_id: {session_id}
reviewed_at: {utcish_timestamp()}
patch_dir: {selected_patch_dir}
decision: {decision}
notes: |
  {notes or "none"}
""",
        encoding="utf-8",
    )
    return ReviewPaths(session_id=session_id, review_file=review_file)


def patch_summary(project: Path, patch_dir: Path | None = None) -> str:
    root = project.resolve()
    selected_patch_dir = patch_dir or latest_patch_dir(root)
    files = [
        selected_patch_dir / "knowledge_patch.md",
        selected_patch_dir / "skill_patch.md",
        selected_patch_dir / "agent_rule_patch.md",
        selected_patch_dir / "questions.md",
        selected_patch_dir / "merge_suggestions.md",
        selected_patch_dir / "composable_units.md",
        selected_patch_dir / "skilllets",
        selected_patch_dir / "prompt_patterns",
        selected_patch_dir / "workflows",
    ]
    lines = [f"Patch directory: {selected_patch_dir}"]
    for path in files:
        status = "present" if path.exists() else "missing"
        lines.append(f"- {path.name}: {status}")
    return "\n".join(lines)


def latest_session_id(project: Path) -> str:
    return latest_session_dir(project).name
