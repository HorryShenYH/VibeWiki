from __future__ import annotations

from pathlib import Path

from .project import ensure_workspace
from .registry import (
    ensure_registry,
    extract_unit_metadata,
    merge_registry_entry,
    read_registry,
    registry_path,
    write_registry,
)
from .review import latest_patch_dir
from .text_utils import append_marked_section, read_text_if_exists


UNIT_DIRS = {
    "skilllets": "skilllet",
    "prompt_patterns": "prompt-pattern",
    "workflows": "workflow",
}

FINDING_WIKI_FILES = {
    "knowledge": "knowledge.md",
    "issue": "known_issues.md",
    "todo": "todos.md",
    "idea": "ideas.md",
    "research_note": "research_notes.md",
    "direction": "directions.md",
}


def _approved(project: Path, session_id: str) -> bool:
    review_file = project / ".vibewiki" / "reviews" / f"{session_id}.yaml"
    return "decision: approved" in read_text_if_exists(review_file)


def _merge_unit_dir(
    root: Path,
    patch_dir: Path,
    session_id: str,
    name: str,
    registry_entries: dict,
) -> list[Path]:
    source_dir = patch_dir / name
    if not source_dir.exists():
        return []

    changed: list[Path] = []
    destination_dir = root / "skills" / name
    unit_label = UNIT_DIRS[name]
    for source in sorted(source_dir.glob("*.md")):
        if source.name == "index.md":
            continue
        body = read_text_if_exists(source)
        if not body:
            continue
        slug = source.stem
        kind, title, keywords = extract_unit_metadata(body, slug)
        target = destination_dir / source.name
        marker = f"<!-- vibewiki:{session_id}:{unit_label}:{slug} -->"
        if append_marked_section(target, marker, body):
            changed.append(target)
        merge_registry_entry(
            registry_entries,
            slug=slug,
            kind=kind,
            title=title,
            keywords=keywords,
            session_id=session_id,
        )

        index = destination_dir / "index.md"
        index_marker = f"<!-- vibewiki:{unit_label}:{slug}:index -->"
        index_body = f"- [{slug}]({source.name})"
        if append_marked_section(index, index_marker, index_body):
            changed.append(index)
    return changed


def _merge_findings(root: Path, patch_dir: Path, session_id: str) -> list[Path]:
    source_dir = patch_dir / "findings"
    if not source_dir.exists():
        return []

    changed: list[Path] = []
    for source in sorted(source_dir.glob("*.md")):
        if source.name == "index.md":
            continue
        body = read_text_if_exists(source)
        if not body:
            continue
        if "__" in source.stem:
            kind, slug = source.stem.split("__", 1)
        else:
            kind, slug = "knowledge", source.stem
        wiki_file = FINDING_WIKI_FILES.get(kind, "knowledge.md")
        target = root / "docs" / "wiki" / wiki_file
        marker = f"<!-- vibewiki:{session_id}:finding:{kind}:{slug} -->"
        if append_marked_section(target, marker, body):
            changed.append(target)
    return changed


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
    registry_file = ensure_registry(root)
    registry_before = read_text_if_exists(registry_file)
    registry_entries = read_registry(registry_path(root))

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
    changed.extend(_merge_findings(root, selected_patch_dir, session_id))
    for unit_dir in UNIT_DIRS:
        changed.extend(_merge_unit_dir(root, selected_patch_dir, session_id, unit_dir, registry_entries))
    write_registry(registry_file, registry_entries)
    if read_text_if_exists(registry_file) != registry_before:
        changed.append(registry_file)

    return list(dict.fromkeys(changed))
