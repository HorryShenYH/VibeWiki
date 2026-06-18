from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterable


def slugify(value: str, fallback: str = "session") -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or fallback


def utcish_timestamp(now: datetime | None = None) -> str:
    current = now or datetime.now().astimezone()
    return current.isoformat(timespec="seconds")


def compact_list(items: Iterable[str]) -> list[str]:
    compacted: list[str] = []
    for item in items:
        text = item.strip()
        if text:
            compacted.append(text)
    return compacted


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text_if_allowed(path: Path, text: str, force: bool = False) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def append_marked_section(path: Path, marker: str, body: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_text_if_exists(path)
    if marker in existing:
        return False
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    path.write_text(f"{existing}{prefix}\n{marker}\n\n{body.rstrip()}\n", encoding="utf-8")
    return True


def markdown_bullets(items: Iterable[str], empty: str = "- Not provided.") -> str:
    values = compact_list(items)
    if not values:
        return empty
    return "\n".join(f"- {value}" for value in values)


def fenced(text: str, language: str = "") -> str:
    clean = text.rstrip()
    if not clean:
        clean = "Not provided."
    return f"```{language}\n{clean}\n```"

