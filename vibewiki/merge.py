from __future__ import annotations

from pathlib import Path

from .project import ensure_workspace
from .review import latest_patch_dir
from .text_utils import append_marked_section, read_text_if_exists


def _approved(project: Path, session_id: str) -> bool:
    review_file = project / ".vibewiki" / "reviews" / f"{session_id}.yaml"
    return "decision: approved" in read_text_if_exists(review_file)


def merge_patches(
    project: Path,
    *,
    patch_dir: Path | None = None,
    require_approved: bool = True,
) -> list[Path]:
    root = project.resolve()
    ensure_workspace(root)
    selected_patch_dir = patch_dir or latest_patch_dir(root)
    session_id = selected_patch_dir.name

    if require_approved and not _approved(root, session_id):
        raise PermissionError(
            f"Patch {session_id} is not approved. Run `vibewiki review --approve` first."
        )

    knowledge = read_text_if_exists(selected_patch_dir / "knowledge_patch.md")
    skill = read_text_if_exists(selected_patch_dir / "skill_patch.md")
    agent_rules = read_text_if_exists(selected_patch_dir / "agent_rule_patch.md")

    changed: list[Path] = []
    knowledge_marker = f"<!-- vibewiki:{session_id}:knowledge -->"
    skill_marker = f"<!-- vibewiki:{session_id}:skill -->"
    agent_marker = f"<!-- vibewiki:{session_id}:agent-rules -->"

    development_notes = root / "docs" / "wiki" / "development_notes.md"
    skill_file = root / "skills" / f"{session_id}.md"
    agents_file = root / "AGENTS.md"

    if append_marked_section(development_notes, knowledge_marker, knowledge):
        changed.append(development_notes)
    if append_marked_section(skill_file, skill_marker, skill):
        changed.append(skill_file)
    if append_marked_section(agents_file, agent_marker, agent_rules):
        changed.append(agents_file)

    return changed

