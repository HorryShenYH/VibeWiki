from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
from typing import Callable
from urllib.parse import urlparse

from .events import append_event, read_events
from .registry import read_registry, registry_path, write_registry
from .text_utils import read_text_if_exists, utcish_timestamp


START_MARKER_RE = re.compile(
    r"(?m)^[ \t]*<!--\s*vibewiki:(?P<descriptor>[^>\n]+?)\s*-->[ \t]*(?:\n|$)"
)

UNIT_COLLECTIONS = {
    "skilllets": "skilllet",
    "prompt_patterns": "prompt-pattern",
    "workflows": "workflow",
}


@dataclass(frozen=True)
class ConversationRecord:
    session_id: str
    title: str
    preview: str
    created_at: str
    recorded_by: str
    source: str
    status: str


@dataclass(frozen=True)
class DeletionImpact:
    session_id: str
    raw_files: int
    candidate_files: int
    review_files: int
    memory_blocks: int
    memory_files: tuple[str, ...]
    shared_files: tuple[str, ...]


@dataclass(frozen=True)
class DeletionResult:
    impact: DeletionImpact
    trash_dir: Path


@dataclass(frozen=True)
class _MemoryBlock:
    descriptor: str
    text: str


def list_conversations(project: Path) -> list[ConversationRecord]:
    root = project.resolve()
    sessions_dir = root / ".vibewiki" / "sessions"
    if not sessions_dir.exists():
        return []

    merged = _merged_session_ids(root)
    records: list[ConversationRecord] = []
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        session_id = session_dir.name
        metadata = _metadata(session_dir / "metadata.yaml")
        session_text = read_text_if_exists(session_dir / "session.md")
        title = _first_content_line(_section(session_text, "Goal")) or session_id
        preview = _first_content_line(_section(session_text, "Final Outcome"))
        if not preview:
            preview = _first_content_line(_section(session_text, "AI Conversation Summary"))
        patch_exists = (root / ".vibewiki" / "patches" / session_id).is_dir()
        if session_id in merged:
            status = "merged"
        elif _approved(root, session_id):
            status = "approved"
        elif patch_exists:
            status = "candidate"
        else:
            status = "captured"
        records.append(
            ConversationRecord(
                session_id=session_id,
                title=title,
                preview=preview or "No outcome recorded yet.",
                created_at=metadata.get("created_at", "") or _date_from_session_id(session_id),
                recorded_by=metadata.get("recorded_by", "unknown") or "unknown",
                source=_source_label(root, metadata),
                status=status,
            )
        )

    return sorted(records, key=lambda item: (item.created_at, item.session_id), reverse=True)


def plan_conversation_deletion(project: Path, session_id: str) -> DeletionImpact:
    root = project.resolve()
    session_dir = _session_dir(root, session_id)
    known_sessions = _known_session_ids(root)
    memory_files: list[str] = []
    shared_files: list[str] = []
    memory_blocks = 0

    for path in _memory_paths(root, session_id):
        text = read_text_if_exists(path)
        blocks = _blocks_for_session(text, session_id)
        if not blocks:
            continue
        memory_blocks += len(blocks)
        relative = _relative(path, root)
        memory_files.append(relative)
        if _has_other_session_source(text, session_id, known_sessions):
            shared_files.append(relative)

    patch_dir = root / ".vibewiki" / "patches" / session_id
    review_files = _review_paths(root, session_id)
    return DeletionImpact(
        session_id=session_id,
        raw_files=_file_count(session_dir),
        candidate_files=_file_count(patch_dir),
        review_files=len(review_files),
        memory_blocks=memory_blocks,
        memory_files=tuple(sorted(set(memory_files))),
        shared_files=tuple(sorted(set(shared_files))),
    )


def delete_conversation(project: Path, session_id: str) -> DeletionResult:
    root = project.resolve()
    session_dir = _session_dir(root, session_id)
    impact = plan_conversation_deletion(root, session_id)
    metadata = _metadata(session_dir / "metadata.yaml")
    trash_dir = _new_trash_dir(root, session_id)
    trash_dir.mkdir(parents=True)

    removed_memory: list[dict[str, object]] = []
    touched_unit_files: set[Path] = set()
    for path in _memory_paths(root, session_id):
        original = read_text_if_exists(path)
        updated, removed = _remove_session_blocks(original, session_id)
        if not removed:
            continue
        _backup_file(path, root, trash_dir)
        removed_memory.append(
            {
                "path": _relative(path, root),
                "blocks": [asdict(block) for block in removed],
            }
        )
        if _unit_collection(path, root):
            touched_unit_files.add(path)
        if updated.strip():
            path.write_text(updated, encoding="utf-8")
        else:
            path.unlink(missing_ok=True)

    for target in sorted(touched_unit_files):
        if target.name == "index.md" or target.exists():
            continue
        collection = _unit_collection(target, root)
        if not collection:
            continue
        index_path = target.parent / "index.md"
        descriptor = f"{UNIT_COLLECTIONS[collection]}:{target.stem}:index"
        original = read_text_if_exists(index_path)
        updated, removed = _remove_exact_descriptor(original, descriptor)
        if removed:
            _backup_file(index_path, root, trash_dir)
            removed_memory.append(
                {
                    "path": _relative(index_path, root),
                    "blocks": [asdict(block) for block in removed],
                }
            )
            index_path.write_text(updated, encoding="utf-8")

    registry_file = registry_path(root)
    if session_id in read_text_if_exists(registry_file):
        _backup_file(registry_file, root, trash_dir)
    registry_removed = _remove_registry_source(root, session_id)
    _move_owned_sources(root, session_dir, session_id, metadata, trash_dir)

    manifest = {
        "schema": 1,
        "deleted_at": utcish_timestamp(),
        "session_id": session_id,
        "impact": asdict(impact),
        "removed_memory": removed_memory,
        "registry_entries_removed": registry_removed,
    }
    (trash_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    append_event(
        root,
        "delete-conversation",
        subject=session_id,
        data={
            "trash_dir": str(trash_dir),
            "memory_blocks": impact.memory_blocks,
            "memory_files": list(impact.memory_files),
            "shared_files_preserved": list(impact.shared_files),
        },
    )
    return DeletionResult(impact=impact, trash_dir=trash_dir)


def _remove_session_blocks(text: str, session_id: str) -> tuple[str, list[_MemoryBlock]]:
    return _remove_matching_blocks(
        text,
        lambda descriptor: descriptor == session_id or descriptor.startswith(f"{session_id}:"),
    )


def _remove_exact_descriptor(text: str, descriptor: str) -> tuple[str, list[_MemoryBlock]]:
    return _remove_matching_blocks(text, lambda candidate: candidate == descriptor)


def _remove_matching_blocks(
    text: str,
    matches_descriptor: Callable[[str], bool],
) -> tuple[str, list[_MemoryBlock]]:
    if not text:
        return text, []
    starts = list(START_MARKER_RE.finditer(text))
    spans: list[tuple[int, int, _MemoryBlock]] = []
    for index, match in enumerate(starts):
        descriptor = match.group("descriptor").strip()
        if not matches_descriptor(descriptor):
            continue
        next_start = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        explicit_end = _end_marker_match(text, descriptor, match.end(), next_start)
        end = explicit_end.end() if explicit_end else next_start
        while end < next_start and text[end] == "\n":
            end += 1
        spans.append(
            (
                match.start(),
                end,
                _MemoryBlock(descriptor=descriptor, text=text[match.start() : end].rstrip()),
            )
        )

    if not spans:
        return text, []
    updated = text
    for start, end, _ in reversed(spans):
        updated = updated[:start] + updated[end:]
    updated = re.sub(r"\n{3,}", "\n\n", updated).rstrip()
    if updated:
        updated += "\n"
    return updated, [block for _, _, block in spans]


def _end_marker_match(text: str, descriptor: str, start: int, end: int) -> re.Match[str] | None:
    pattern = re.compile(
        rf"(?m)^[ \t]*<!--\s*/vibewiki:{re.escape(descriptor)}\s*-->[ \t]*(?:\n|$)"
    )
    match = pattern.search(text, start, end)
    return match


def _blocks_for_session(text: str, session_id: str) -> list[_MemoryBlock]:
    _, blocks = _remove_session_blocks(text, session_id)
    return blocks


def _memory_paths(root: Path, session_id: str) -> list[Path]:
    paths: set[Path] = set()
    for directory in (root / "docs" / "wiki", root / "skills"):
        if directory.exists():
            paths.update(path.resolve() for path in directory.rglob("*.md") if path.is_file())
    agents = root / "AGENTS.md"
    if agents.is_file():
        paths.add(agents.resolve())
    for event in read_events(root, event_type="merge", limit=None):
        if str(event.get("subject", "")).strip() != session_id:
            continue
        data = event.get("data", {})
        changed = data.get("changed", []) if isinstance(data, dict) else []
        if not isinstance(changed, list):
            continue
        for raw_path in changed:
            path = Path(str(raw_path)).expanduser()
            path = path if path.is_absolute() else root / path
            resolved = path.resolve()
            if resolved.suffix == ".md" and resolved.is_file() and _is_within(resolved, root):
                paths.add(resolved)
    return sorted(paths)


def _move_owned_sources(
    root: Path,
    session_dir: Path,
    session_id: str,
    metadata: dict[str, str],
    trash_dir: Path,
) -> None:
    shutil.move(str(session_dir), str(trash_dir / "session"))
    patch_dir = root / ".vibewiki" / "patches" / session_id
    if patch_dir.is_dir():
        shutil.move(str(patch_dir), str(trash_dir / "patch"))
    review_targets = _review_paths(root, session_id)
    if review_targets:
        (trash_dir / "reviews").mkdir()
        for path in review_targets:
            shutil.move(str(path), str(trash_dir / "reviews" / path.name))

    imported_from = metadata.get("imported_from", "")
    if not imported_from:
        return
    source = Path(imported_from).expanduser()
    inbox = (root / ".vibewiki" / "inbox").resolve()
    try:
        owned_source = source.resolve()
        owned_source.relative_to(inbox)
    except (OSError, ValueError):
        return
    if owned_source.is_file():
        (trash_dir / "source").mkdir()
        shutil.move(str(owned_source), str(trash_dir / "source" / owned_source.name))


def _remove_registry_source(root: Path, session_id: str) -> list[str]:
    path = registry_path(root)
    entries = read_registry(path)
    changed = False
    removed: list[str] = []
    for slug, entry in list(entries.items()):
        if session_id not in entry.evidence_sessions:
            continue
        remaining = tuple(item for item in entry.evidence_sessions if item != session_id)
        changed = True
        if not remaining:
            removed.append(slug)
            del entries[slug]
            continue
        entries[slug] = type(entry)(
            slug=entry.slug,
            kind=entry.kind,
            title=entry.title,
            status=entry.status,
            aliases=entry.aliases,
            keywords=entry.keywords,
            evidence_sessions=remaining,
        )
    if changed:
        write_registry(path, entries)
    return removed


def _review_paths(root: Path, session_id: str) -> list[Path]:
    reviews_dir = root / ".vibewiki" / "reviews"
    if not reviews_dir.exists():
        return []
    return sorted(
        path
        for path in reviews_dir.glob(f"{session_id}.*")
        if path.is_file() and path.name.startswith(f"{session_id}.")
    )


def _backup_file(path: Path, root: Path, trash_dir: Path) -> None:
    if not path.is_file():
        return
    relative = Path(_relative(path, root))
    backup = trash_dir / "memory_before_delete" / relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)


def _has_other_session_source(text: str, session_id: str, known_sessions: set[str]) -> bool:
    for match in START_MARKER_RE.finditer(text):
        descriptor = match.group("descriptor").strip()
        owner = descriptor.split(":", 1)[0]
        if owner != session_id and owner in known_sessions:
            return True
    return False


def _known_session_ids(root: Path) -> set[str]:
    values: set[str] = set()
    for name in ("sessions", "patches"):
        directory = root / ".vibewiki" / name
        if directory.exists():
            values.update(path.name for path in directory.iterdir() if path.is_dir())
    return values


def _merged_session_ids(root: Path) -> set[str]:
    merged: set[str] = set()
    deleted: set[str] = set()
    for event in read_events(root, limit=None):
        subject = str(event.get("subject", "")).strip()
        if not subject:
            continue
        if event.get("type") == "merge":
            merged.add(subject)
        elif event.get("type") == "delete-conversation":
            deleted.add(subject)
    return merged - deleted


def _approved(root: Path, session_id: str) -> bool:
    return "decision: approved" in read_text_if_exists(
        root / ".vibewiki" / "reviews" / f"{session_id}.yaml"
    )


def _metadata(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text_if_exists(path).splitlines():
        if not line or line[0].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        clean_key = key.strip()
        if clean_key:
            values[clean_key] = value.strip().strip('"\'')
    return values


def _source_label(root: Path, metadata: dict[str, str]) -> str:
    imported_url = metadata.get("imported_url", "")
    if imported_url:
        host = urlparse(imported_url).netloc.removeprefix("www.")
        if "chatgpt.com" in host:
            return "ChatGPT share"
        if "claude.ai" in host:
            return "Claude share"
        return host or "Shared link"
    imported_from = metadata.get("imported_from", "")
    if imported_from:
        source = Path(imported_from)
        inbox = (root / ".vibewiki" / "inbox").resolve()
        try:
            source.resolve().relative_to(inbox)
            return "Pasted Markdown"
        except (OSError, ValueError):
            return source.name or "Markdown file"
    return "Quick result"


def _section(markdown: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)",
        markdown,
    )
    return match.group("body").strip() if match else ""


def _first_content_line(value: str) -> str:
    for line in value.splitlines():
        clean = line.strip().lstrip("- ").strip()
        if clean and clean != "Not provided.":
            return re.sub(r"[`*_]+", "", clean)
    return ""


def _date_from_session_id(session_id: str) -> str:
    match = re.match(r"(\d{8})-(\d{6})", session_id)
    if not match:
        return ""
    date = match.group(1)
    time = match.group(2)
    return f"{date[:4]}-{date[4:6]}-{date[6:]}T{time[:2]}:{time[2:4]}:{time[4:]}"


def _new_trash_dir(root: Path, session_id: str) -> Path:
    trash_root = root / ".vibewiki" / "trash"
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    candidate = trash_root / f"{stamp}-{session_id}"
    suffix = 2
    while candidate.exists():
        candidate = trash_root / f"{stamp}-{session_id}-{suffix}"
        suffix += 1
    return candidate


def _session_dir(root: Path, session_id: str) -> Path:
    if not session_id:
        raise ValueError("Conversation is required.")
    base = (root / ".vibewiki" / "sessions").resolve()
    selected = (base / session_id).resolve()
    if selected.parent != base or not selected.is_dir():
        raise FileNotFoundError(f"Conversation not found: {session_id}")
    return selected


def _unit_collection(path: Path, root: Path) -> str:
    for collection in UNIT_COLLECTIONS:
        directory = (root / "skills" / collection).resolve()
        try:
            path.resolve().relative_to(directory)
            return collection
        except ValueError:
            continue
    return ""


def _file_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob("*") if item.is_file())


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
