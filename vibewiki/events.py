from __future__ import annotations

import getpass
import json
from pathlib import Path
import re
import uuid

from .text_utils import read_text_if_exists, utcish_timestamp


EVENTS_FILE = "events.jsonl"


def events_path(project: Path) -> Path:
    return project.resolve() / ".vibewiki" / EVENTS_FILE


def append_event(
    project: Path,
    event_type: str,
    *,
    subject: str = "",
    data: dict[str, object] | None = None,
) -> dict[str, object]:
    path = events_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 1,
        "id": uuid.uuid4().hex[:12],
        "at": utcish_timestamp(),
        "actor": getpass.getuser(),
        "type": event_type,
        "subject": subject,
        "data": _jsonable(data or {}),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return payload


def read_events(
    project: Path,
    *,
    event_type: str = "",
    limit: int | None = None,
) -> list[dict[str, object]]:
    path = events_path(project)
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if event_type and payload.get("type") != event_type:
            continue
        events.append(payload)
    if limit is not None and limit > 0:
        return events[-limit:]
    return events


def recorded_by_for_memory(project: Path, source: Path, *, section: str = "") -> str:
    root = project.resolve()
    session_id = _session_id_for_memory(root, source, section)
    if not session_id:
        return "unknown"
    metadata = read_text_if_exists(
        root / ".vibewiki" / "sessions" / session_id / "metadata.yaml"
    )
    match = re.search(r"^recorded_by:\s*(.+)$", metadata, re.MULTILINE)
    if match and match.group(1).strip():
        return match.group(1).strip()
    priorities = {
        "capture": 3,
        "import-markdown": 3,
        "import-url": 3,
        "distill": 2,
    }
    selected: tuple[int, str] | None = None
    for event in read_events(root):
        if str(event.get("subject", "")).strip() != session_id:
            continue
        priority = priorities.get(str(event.get("type", "")), 0)
        actor = str(event.get("actor", "")).strip()
        if not priority or not actor:
            continue
        if selected is None or priority >= selected[0]:
            selected = (priority, actor)
    return selected[1] if selected else "unknown"


def _session_id_for_memory(root: Path, source: Path, section: str) -> str:
    try:
        relative = source.resolve().relative_to(root)
    except ValueError:
        relative = source
    parts = relative.parts
    for parent in ("patches", "sessions"):
        if len(parts) >= 3 and parts[:2] == (".vibewiki", parent):
            return parts[2]

    text = read_text_if_exists(source)
    if not text:
        return ""
    marker_pattern = re.compile(r"<!--\s*vibewiki:([^:>]+):[^>]*-->")
    if section and section != "Document":
        heading_pattern = re.compile(
            rf"^#{{1,3}}\s+{re.escape(section)}\s*$",
            re.MULTILINE,
        )
        direct_marker = re.compile(r"<!--\s*vibewiki:([^:>]+):[^>]*-->\s*$")
        for heading in heading_pattern.finditer(text):
            marker = direct_marker.search(text[: heading.start()])
            if marker:
                return marker.group(1).strip()
    sessions = {match.group(1).strip() for match in marker_pattern.finditer(text)}
    return next(iter(sessions)) if len(sessions) == 1 else ""


def format_events(events: list[dict[str, object]], *, verbose: bool = False) -> str:
    if not events:
        return "No VibeWiki events recorded.\n"
    lines: list[str] = []
    for event in events:
        at = str(event.get("at", "")).strip()
        event_type = str(event.get("type", "")).strip()
        actor = str(event.get("actor", "")).strip()
        subject = str(event.get("subject", "")).strip()
        head = f"{at}  {event_type}"
        if subject:
            head += f"  {subject}"
        if actor:
            head += f"  @{actor}"
        lines.append(head)
        if verbose:
            data = event.get("data", {})
            if isinstance(data, dict) and data:
                for key, value in data.items():
                    lines.append(f"  {key}: {_compact(value)}")
    return "\n".join(lines).rstrip() + "\n"


def _jsonable(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(child) for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _compact(value: object, limit: int = 180) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text
