from __future__ import annotations

import getpass
import json
from pathlib import Path
import uuid

from .text_utils import utcish_timestamp


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
