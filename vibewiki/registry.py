from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .text_utils import compact_list, read_text_if_exists, slugify


KEYWORD_STOPWORDS = {
    "about",
    "active",
    "against",
    "and",
    "before",
    "candidate",
    "confidence",
    "evidence",
    "existing",
    "from",
    "generated",
    "implementation",
    "inputs",
    "into",
    "kind",
    "medium",
    "outputs",
    "purpose",
    "related",
    "session",
    "should",
    "skilllet",
    "status",
    "steps",
    "that",
    "the",
    "this",
    "units",
    "update",
    "use",
    "verification",
    "when",
    "with",
}

SHORT_KEYWORDS = {
    "cau",
    "dfe",
    "f5",
    "mae",
    "rtl",
    "rmse",
}

REGISTRY_TEMPLATE = """# VibeWiki skill registry
# This file lets later sessions update existing skilllets instead of creating
# redundant near-duplicates.
version: 1
units:
"""


@dataclass(frozen=True)
class RegistryEntry:
    slug: str
    kind: str
    title: str
    status: str = "active"
    aliases: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    evidence_sessions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegistryMatch:
    slug: str
    score: int
    reason: str
    reuse: bool


def registry_path(project: Path) -> Path:
    return project / ".vibewiki" / "skill_registry.yaml"


def ensure_registry(project: Path) -> Path:
    path = registry_path(project)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(REGISTRY_TEMPLATE, encoding="utf-8")
    return path


def _strip_value(value: str) -> str:
    clean = value.strip()
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in {"'", '"'}:
        return clean[1:-1]
    return clean


def _unique(items: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _strip_value(str(item))
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        values.append(clean)
    return tuple(values)


def read_registry(path: Path) -> dict[str, RegistryEntry]:
    text = read_text_if_exists(path)
    entries: dict[str, dict[str, object]] = {}
    current_slug = ""
    current_list = ""

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()

        if indent == 2 and stripped.endswith(":"):
            current_slug = stripped[:-1]
            current_list = ""
            entries.setdefault(current_slug, {"slug": current_slug})
            continue

        if not current_slug:
            continue

        if indent == 4 and ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = _strip_value(value)
            if value:
                entries[current_slug][key] = value
                current_list = ""
            else:
                entries[current_slug][key] = []
                current_list = key
            continue

        if indent >= 6 and current_list and stripped.startswith("- "):
            value = _strip_value(stripped[2:])
            values = entries[current_slug].setdefault(current_list, [])
            if isinstance(values, list):
                values.append(value)

    parsed: dict[str, RegistryEntry] = {}
    for slug, data in entries.items():
        parsed[slug] = RegistryEntry(
            slug=slug,
            kind=str(data.get("kind", "skilllet")),
            title=str(data.get("title", slug.replace("-", " ").title())),
            status=str(data.get("status", "active")),
            aliases=_unique(tuple(data.get("aliases", []))),  # type: ignore[arg-type]
            keywords=_unique(tuple(data.get("keywords", []))),  # type: ignore[arg-type]
            evidence_sessions=_unique(tuple(data.get("evidence_sessions", []))),  # type: ignore[arg-type]
        )
    return parsed


def _yaml_scalar(value: str) -> str:
    clean = value.replace("\n", " ").strip()
    if not clean:
        return '""'
    if re.search(r"[:#\[\]{}]|^\s|\s$", clean):
        return '"' + clean.replace('"', '\\"') + '"'
    return clean


def _yaml_list(values: tuple[str, ...]) -> str:
    if not values:
        return "\n"
    return "\n" + "".join(f"      - {_yaml_scalar(value)}\n" for value in values)


def write_registry(path: Path, entries: dict[str, RegistryEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [REGISTRY_TEMPLATE.rstrip()]
    for slug in sorted(entries):
        entry = entries[slug]
        lines.extend(
            [
                f"  {slug}:",
                f"    kind: {_yaml_scalar(entry.kind)}",
                f"    title: {_yaml_scalar(entry.title)}",
                f"    status: {_yaml_scalar(entry.status)}",
                "    aliases:" + _yaml_list(entry.aliases).rstrip(),
                "    keywords:" + _yaml_list(entry.keywords).rstrip(),
                "    evidence_sessions:" + _yaml_list(entry.evidence_sessions).rstrip(),
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalize_keyword(value: str) -> str:
    clean = value.strip().lower()
    clean = re.sub(r"`+", "", clean)
    clean = re.sub(r"[^a-z0-9_+./-]+", "-", clean).strip("-")
    return clean


def unit_keywords(*parts: str, limit: int = 32) -> tuple[str, ...]:
    values: list[str] = []
    for text in parts:
        values.extend(re.findall(r"`([^`]{2,80})`", text))
        values.extend(re.findall(r"\b[A-Za-z][A-Za-z0-9_+./-]{2,}\b", text))
    normalized = [normalize_keyword(item) for item in values]
    return _unique(
        tuple(
            item
            for item in normalized
            if item
            and (len(item) >= 4 or item in SHORT_KEYWORDS)
            and item not in KEYWORD_STOPWORDS
            and not item.startswith("202")
        )
    )[:limit]


def _entry_terms(entry: RegistryEntry) -> set[str]:
    terms = {entry.slug, *entry.aliases, *entry.keywords}
    terms.add(slugify(entry.title, fallback=entry.slug))
    return {normalize_keyword(term) for term in terms if normalize_keyword(term)}


def match_registry(
    entries: dict[str, RegistryEntry],
    *,
    kind: str,
    proposed_slug: str,
    title: str,
    keywords: tuple[str, ...],
) -> RegistryMatch | None:
    proposed_terms = {
        normalize_keyword(proposed_slug),
        normalize_keyword(slugify(title, fallback=proposed_slug)),
        *[normalize_keyword(keyword) for keyword in keywords],
    }
    proposed_terms = {item for item in proposed_terms if item}

    best: RegistryMatch | None = None
    for slug, entry in entries.items():
        if entry.status == "deprecated":
            continue
        if entry.kind != kind:
            continue
        entry_terms = _entry_terms(entry)

        if normalize_keyword(proposed_slug) == normalize_keyword(slug):
            match = RegistryMatch(slug=slug, score=100, reason="exact slug", reuse=True)
        elif normalize_keyword(proposed_slug) in entry_terms:
            match = RegistryMatch(slug=slug, score=95, reason="alias match", reuse=True)
        else:
            overlap = sorted(proposed_terms & entry_terms)
            overlap_count = len(overlap)
            if overlap_count >= 3:
                match = RegistryMatch(
                    slug=slug,
                    score=min(90, 45 + overlap_count * 10),
                    reason="keyword overlap: " + ", ".join(overlap[:6]),
                    reuse=False,
                )
            else:
                continue

        if best is None or match.score > best.score:
            best = match
    return best


def merge_registry_entry(
    entries: dict[str, RegistryEntry],
    *,
    slug: str,
    kind: str,
    title: str,
    keywords: tuple[str, ...],
    session_id: str,
) -> dict[str, RegistryEntry]:
    existing = entries.get(slug)
    aliases = (slugify(title, fallback=slug),)
    if existing:
        entries[slug] = RegistryEntry(
            slug=slug,
            kind=existing.kind or kind,
            title=existing.title or title,
            status=existing.status or "active",
            aliases=_unique((*existing.aliases, *aliases)),
            keywords=_unique((*existing.keywords, *keywords)),
            evidence_sessions=_unique((*existing.evidence_sessions, session_id)),
        )
    else:
        entries[slug] = RegistryEntry(
            slug=slug,
            kind=kind,
            title=title,
            aliases=_unique(aliases),
            keywords=_unique(keywords),
            evidence_sessions=(session_id,),
        )
    return entries


def extract_unit_metadata(markdown: str, fallback_slug: str) -> tuple[str, str, tuple[str, ...]]:
    kind = "skilllet"
    title = fallback_slug.replace("-", " ").title()
    for line in markdown.splitlines():
        if line.startswith("# "):
            heading = line[2:].strip()
            if ":" in heading:
                label, rest = heading.split(":", 1)
                kind = label.strip().lower().replace(" ", "_")
                title = rest.strip()
            else:
                title = heading
        elif line.startswith("Kind:"):
            kind = line.split(":", 1)[1].strip()
        if title != fallback_slug.replace("-", " ").title() and kind:
            break

    keywords = unit_keywords(title, markdown)
    return kind, title, keywords


def render_merge_suggestions(session_id: str, suggestions: list[str]) -> str:
    suggestion_text = "\n".join(f"- {item}" for item in compact_list(suggestions))
    if not suggestion_text:
        suggestion_text = "- Not provided."
    return f"""# Merge Suggestions

Session: {session_id}

These are registry-based hints for human review. High-confidence matches are
reused automatically by slug; lower-confidence matches stay as suggestions.

## Suggestions

{suggestion_text}
"""
