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

CURATION_SCHEMA = 1
MAX_CUSTOM_TITLE = 160
MAX_NOTE = 2000
MAX_TAGS = 20
MAX_TAG_LENGTH = 40


@dataclass(frozen=True)
class ConversationRecord:
    session_id: str
    title: str
    preview: str
    created_at: str
    recorded_by: str
    source: str
    status: str
    pinned: bool = False
    tags: tuple[str, ...] = ()
    custom_title: str = ""
    note: str = ""


@dataclass(frozen=True)
class ConversationSearchHit:
    session_id: str
    title: str
    snippet: str
    score: int


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
class ConversationDetail:
    conversation: ConversationRecord
    transcript: str
    transcript_file: str
    impact: DeletionImpact


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
    flags = _read_conversation_flags(root)
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
        curation = flags.get(session_id, {})
        custom_title = str(curation.get("custom_title", "")).strip()
        tags = _clean_tags(curation.get("tags", []))
        records.append(
            ConversationRecord(
                session_id=session_id,
                title=custom_title or title,
                preview=preview or "No outcome recorded yet.",
                created_at=metadata.get("created_at", "") or _date_from_session_id(session_id),
                recorded_by=metadata.get("recorded_by", "unknown") or "unknown",
                source=_source_label(root, metadata),
                status=status,
                pinned=bool(curation.get("pinned", False)),
                tags=tags,
                custom_title=custom_title,
                note=str(curation.get("note", "")).strip(),
            )
        )

    return sorted(
        records,
        key=lambda item: (item.pinned, item.created_at, item.session_id),
        reverse=True,
    )


def get_conversation_detail(project: Path, session_id: str) -> ConversationDetail:
    root = project.resolve()
    session_dir = _session_dir(root, session_id)
    conversation = next(
        (item for item in list_conversations(root) if item.session_id == session_id),
        None,
    )
    if conversation is None:
        raise FileNotFoundError(f"Conversation not found: {session_id}")
    raw_path = session_dir / "raw_session.md"
    transcript_path = raw_path if raw_path.is_file() else session_dir / "session.md"
    return ConversationDetail(
        conversation=conversation,
        transcript=read_text_if_exists(transcript_path),
        transcript_file=transcript_path.name,
        impact=plan_conversation_deletion(root, session_id),
    )


def search_conversations(
    project: Path,
    query: str,
    *,
    limit: int = 50,
) -> list[ConversationSearchHit]:
    root = project.resolve()
    needle = query.strip().casefold()
    if not needle:
        return []
    hits: list[tuple[ConversationSearchHit, bool, str]] = []
    for conversation in list_conversations(root):
        session_dir = _session_dir(root, conversation.session_id)
        raw = read_text_if_exists(session_dir / "raw_session.md")
        normalized = read_text_if_exists(session_dir / "session.md")
        metadata = " ".join(
            (
                conversation.title,
                conversation.preview,
                conversation.recorded_by,
                conversation.source,
                " ".join(conversation.tags),
                conversation.note,
                conversation.session_id,
            )
        )
        score = 0
        source = ""
        if needle in conversation.title.casefold():
            score += 8
            source = conversation.title
        if needle in conversation.preview.casefold():
            score += 5
            source = source or conversation.preview
        if needle in metadata.casefold():
            score += 3
            source = source or metadata
        for content in (raw, normalized):
            if needle in content.casefold():
                score += 2
                source = source or content
                break
        if not score:
            continue
        hit = ConversationSearchHit(
            session_id=conversation.session_id,
            title=conversation.title,
            snippet=_search_snippet(source, query),
            score=score,
        )
        hits.append((hit, conversation.pinned, conversation.created_at))
    hits.sort(key=lambda item: (item[0].score, item[1], item[2]), reverse=True)
    return [item[0] for item in hits[: max(1, min(limit, 200))]]


def update_conversation_flags(
    project: Path,
    session_id: str,
    *,
    pinned: bool,
    tags: list[str] | tuple[str, ...],
    custom_title: str,
    note: str,
) -> ConversationRecord:
    root = project.resolve()
    _session_dir(root, session_id)
    clean_title = custom_title.strip()
    clean_note = note.strip()
    clean_tags = _clean_tags(tags)
    if len(clean_title) > MAX_CUSTOM_TITLE:
        raise ValueError(f"Conversation title exceeds {MAX_CUSTOM_TITLE} characters.")
    if len(clean_note) > MAX_NOTE:
        raise ValueError(f"Conversation note exceeds {MAX_NOTE} characters.")
    flags = _read_conversation_flags(root)
    next_value = {
        "pinned": bool(pinned),
        "tags": list(clean_tags),
        "custom_title": clean_title,
        "note": clean_note,
    }
    if pinned or clean_tags or clean_title or clean_note:
        flags[session_id] = next_value
    else:
        flags.pop(session_id, None)
    _write_conversation_flags(root, flags)
    return next(
        item for item in list_conversations(root) if item.session_id == session_id
    )


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
    if bool(_read_conversation_flags(root).get(session_id, {}).get("pinned", False)):
        raise ValueError("Pinned conversations cannot be removed. Unpin this conversation first.")
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
    _remove_conversation_flags(root, session_id)

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


def _conversation_flags_path(root: Path) -> Path:
    return root / ".vibewiki" / "private" / "conversation_flags.json"


def _read_conversation_flags(root: Path) -> dict[str, dict[str, object]]:
    path = _conversation_flags_path(root)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Conversation curation is invalid; refusing to overwrite {path}."
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            f"Conversation curation is invalid; refusing to overwrite {path}."
        )
    sessions = payload.get("sessions", {})
    if not isinstance(sessions, dict):
        raise ValueError(
            f"Conversation curation is invalid; refusing to overwrite {path}."
        )
    return {
        str(session_id): value
        for session_id, value in sessions.items()
        if isinstance(value, dict)
    }


def _write_conversation_flags(root: Path, flags: dict[str, dict[str, object]]) -> None:
    path = _conversation_flags_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": CURATION_SCHEMA,
        "sessions": dict(sorted(flags.items())),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
    )
    temporary.replace(path)


def _remove_conversation_flags(root: Path, session_id: str) -> None:
    flags = _read_conversation_flags(root)
    if flags.pop(session_id, None) is None:
        return
    _write_conversation_flags(root, flags)


def _clean_tags(values: object) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    tags: list[str] = []
    for value in values:
        clean = str(value).strip()
        if not clean or clean in tags:
            continue
        if len(clean) > MAX_TAG_LENGTH:
            raise ValueError(f"Conversation tags must be at most {MAX_TAG_LENGTH} characters.")
        tags.append(clean)
        if len(tags) > MAX_TAGS:
            raise ValueError(f"A conversation can have at most {MAX_TAGS} tags.")
    return tuple(tags)


def _search_snippet(text: str, query: str, *, radius: int = 110) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return "Matched conversation metadata."
    index = compact.casefold().find(query.strip().casefold())
    if index < 0:
        return compact[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(compact), index + len(query.strip()) + radius)
    snippet = compact[start:end].strip(" -#>*_" + chr(96))
    if start:
        snippet = "..." + snippet
    if end < len(compact):
        snippet += "..."
    return snippet


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
