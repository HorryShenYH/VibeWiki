from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
from typing import Any

from .events import recorded_by_for_memory
from .memory_cards import MemoryCard, collect_memory_cards, search_memory_cards
from .retrieval import collect_memory_chunks, search_memory
from .text_utils import read_text_if_exists


def build_agent_brief(project: Path) -> dict[str, Any]:
    root = project.resolve()
    _require_workspace(root)
    chunks = [
        chunk
        for chunk in collect_memory_chunks(root, scope="approved")
        if _useful_text(chunk.text)
    ]
    kind_counts = Counter(_kind(chunk.kind) for chunk in chunks)
    kinds: list[dict[str, Any]] = []
    for kind, count in kind_counts.most_common():
        examples: list[str] = []
        for chunk in chunks:
            if _kind(chunk.kind) != kind:
                continue
            label = chunk.title if chunk.section == "Document" else chunk.section
            value = _compact(label or chunk.title, 90)
            if value and value not in examples:
                examples.append(value)
            if len(examples) == 2:
                break
        kinds.append({"kind": kind, "count": count, "examples": examples})

    rules = _agent_rules(root)
    sources = [
        path
        for path in ["AGENTS.md", "docs/wiki/project_brief.md"]
        if (root / path).exists()
    ]
    return {
        "schema": 1,
        "project": root.name,
        "summary": _project_summary(root),
        "memory": {
            "default_scope": "approved",
            "indexed_documents": len({chunk.source for chunk in chunks}),
            "indexed_sections": len(chunks),
            "kinds": kinds,
        },
        "rules": rules,
        "policy": {
            "candidate_memory": "excluded unless explicitly requested",
            "new_memory": "capture as candidate and require human review before reuse",
            "reading": "search first, then read only the selected sources",
        },
        "recommended_flow": [
            "Call vibewiki_guard with the task before editing.",
            "Call vibewiki_search for task-specific memory.",
            "Call vibewiki_read only for selected refs.",
        ],
        "sources": sources,
    }


def search_agent_memory(
    project: Path,
    query: str,
    *,
    include_candidates: bool = False,
    max_items: int = 6,
    kinds: list[str] | tuple[str, ...] | None = None,
    use_embeddings: bool = True,
) -> dict[str, Any]:
    root = project.resolve()
    _require_workspace(root)
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query is required")
    limit = _clamp(max_items, 1, 12)
    scope = "all" if include_candidates else "approved"
    selected_kinds = {_kind(value) for value in (kinds or []) if str(value).strip()}
    ranked: list[tuple[float, str, dict[str, Any]]] = []

    card_results = search_memory_cards(
        root,
        clean_query,
        scope=scope,
        max_items=min(limit * 4, 48),
        ensure=False,
    )
    useful_card_results = [result for result in card_results if _useful_card(result.card)]
    max_card_score = max((result.score for result in useful_card_results), default=1.0)
    for result in useful_card_results:
        card = result.card
        if selected_kinds and _kind(card.kind) not in selected_kinds:
            continue
        source = _relative(card.source, root)
        ranked.append(
            (
                result.score / max_card_score,
                source,
                _card_item(card, source, result.score),
            )
        )

    chunk_results = search_memory(
        root,
        clean_query,
        scope=scope,
        max_items=min(limit * 4, 48),
        snippet_chars=360,
        use_embeddings=use_embeddings,
        ensure=False,
    )
    useful_chunk_results = [result for result in chunk_results if _useful_text(result.snippet)]
    max_chunk_score = max((result.score for result in useful_chunk_results), default=1.0)
    for result in useful_chunk_results:
        chunk = result.chunk
        if selected_kinds and _kind(chunk.kind) not in selected_kinds:
            continue
        source = _relative(chunk.source, root)
        rank_score = result.score / max_chunk_score
        if chunk.section:
            rank_score += 0.05
        ranked.append(
            (
                rank_score,
                source,
                {
                    "id": chunk.id,
                    "ref": chunk.id,
                    "status": chunk.status,
                    "kind": _kind(chunk.kind),
                    "title": chunk.title,
                    "section": chunk.section,
                    "summary": _compact(result.snippet, 360),
                    "confidence": "high" if chunk.status == "approved" else "medium",
                    "recorded_by": recorded_by_for_memory(
                        root,
                        chunk.source,
                        section=chunk.section,
                    ),
                    "source": source,
                    "score": round(result.score, 4),
                },
            )
        )

    best_by_source: dict[str, tuple[float, dict[str, Any]]] = {}
    for rank_score, source, item in ranked:
        current = best_by_source.get(source)
        if current is None or rank_score > current[0]:
            best_by_source[source] = (rank_score, item)
    items = [
        item
        for _, item in sorted(
            best_by_source.values(),
            key=lambda value: value[0],
            reverse=True,
        )[:limit]
    ]

    payload: dict[str, Any] = {
        "query": clean_query,
        "scope": scope,
        "count": len(items),
        "items": items,
    }
    if include_candidates:
        payload["warning"] = "Candidate memory is unreviewed and must not be treated as fact."
    return payload


def read_agent_memory(
    project: Path,
    refs: list[str] | tuple[str, ...],
    *,
    include_candidates: bool = False,
    max_chars_per_item: int = 4000,
) -> dict[str, Any]:
    root = project.resolve()
    _require_workspace(root)
    clean_refs = [str(value).strip() for value in refs if str(value).strip()]
    if not clean_refs:
        raise ValueError("at least one ref is required")
    if len(clean_refs) > 6:
        raise ValueError("at most 6 refs can be read at once")
    scope = "all" if include_candidates else "approved"
    char_limit = _clamp(max_chars_per_item, 300, 12000)
    index = _read_index(root, scope=scope)
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for ref in clean_refs:
        entry = index.get(ref)
        if entry is None:
            errors.append(
                {
                    "ref": ref,
                    "error": "not found in the allowed memory scope",
                }
            )
            continue
        source = str(entry["source"])
        section = str(entry.get("section", ""))
        key = (source, section)
        if key in seen:
            continue
        seen.add(key)
        text = str(entry["text"]).strip()
        truncated = len(text) > char_limit
        if truncated:
            text = text[:char_limit].rstrip() + "..."
        items.append(
            {
                "ref": ref,
                "status": entry["status"],
                "kind": entry["kind"],
                "title": entry["title"],
                "section": section,
                "source": source,
                "recorded_by": entry["recorded_by"],
                "text": text,
                "truncated": truncated,
            }
        )

    payload: dict[str, Any] = {
        "scope": scope,
        "count": len(items),
        "items": items,
        "errors": errors,
    }
    if include_candidates:
        payload["warning"] = "Candidate memory is unreviewed and must not be treated as fact."
    return payload


def guard_agent_task(project: Path, task: str, *, max_items: int = 6) -> dict[str, Any]:
    clean_task = task.strip()
    if not clean_task:
        raise ValueError("task is required")
    limit = _clamp(max_items, 1, 10)
    query = f"{clean_task} known issue warning failure deprecated verification workflow rule"
    search = search_agent_memory(
        project,
        query,
        include_candidates=False,
        max_items=min(limit * 2, 12),
    )
    groups: dict[str, list[dict[str, Any]]] = {
        "warnings": [],
        "workflows": [],
        "rules": [],
        "context": [],
    }
    for item in search["items"]:
        kind = str(item.get("kind", "")).lower()
        title = str(item.get("title", "")).lower()
        summary = str(item.get("summary", "")).lower()
        haystack = " ".join(
            [
                kind,
                title,
                summary,
            ]
        )
        if _contains_any(kind, ("workflow", "skilllet")) or _contains_any(
            title, ("workflow", "procedure", "runbook")
        ):
            target = "workflows"
        elif _contains_any(kind, ("agent_rule", "rule")) or _contains_any(
            haystack, ("agent rule", "must ", "do not ", "before editing")
        ):
            target = "rules"
        elif _contains_any(kind, ("issue", "warning", "caveat")) or _contains_any(
            title, ("known issue", "warning", "risk", "failure", "deprecated", "caveat")
        ):
            target = "warnings"
        elif "todo" not in title and _contains_any(
            summary, ("must not", "do not", "can fail", "failure", "deprecated", "caveat")
        ):
            target = "warnings"
        else:
            target = "context"
        if sum(len(values) for values in groups.values()) < limit:
            groups[target].append(item)

    found = sum(len(values) for values in groups.values())
    return {
        "task": clean_task,
        "scope": "approved",
        "status": "memory_found" if found else "no_matching_approved_memory",
        **groups,
        "instruction": "Use these records as task constraints; read selected refs before editing.",
    }


def _card_item(card: MemoryCard, source: str, score: float) -> dict[str, Any]:
    methods = [_compact(value, 140) for value in card.method[:2] if value.strip()]
    return {
        "id": card.id,
        "ref": card.id,
        "status": card.status,
        "kind": _kind(card.kind),
        "title": card.subject or card.title,
        "summary": _compact(card.claim or card.result, 320),
        "methods": methods,
        "confidence": card.confidence,
        "recorded_by": card.actor,
        "source": source,
        "score": round(score, 4),
    }


def _useful_card(card: MemoryCard) -> bool:
    return _useful_text(card.claim or card.result or "")


def _useful_text(value: str) -> bool:
    clean = _compact(value, 500).lower()
    if len(clean) < 20:
        return False
    boilerplate_markers = (
        "this wiki contains human-reviewed",
        "use this page for verified recurring",
        "reviewed vibewiki knowledge patches will be appended",
        "reviewed facts, explanations",
        "reviewed follow-up tasks",
        "reviewed ideas and sparks",
        "reviewed hypotheses, experiment notes",
        "reviewed project or research directions",
        "reusable project procedures generated",
        "small capability units extracted",
        "reusable prompts and task",
        "larger procedures that compose",
    )
    return not any(marker in clean[:260] for marker in boilerplate_markers)


def _read_index(root: Path, *, scope: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for card in collect_memory_cards(root, scope=scope, ensure=False):
        source = _relative(card.source, root)
        entry = {
            "status": card.status,
            "kind": _kind(card.kind),
            "title": card.subject or card.title,
            "section": "",
            "source": source,
            "recorded_by": card.actor,
            "text": read_text_if_exists(card.source),
        }
        index.setdefault(source, entry)
        index[card.id] = entry
    for chunk in collect_memory_chunks(root, scope=scope):
        source = _relative(chunk.source, root)
        full_entry = {
            "status": chunk.status,
            "kind": _kind(chunk.kind),
            "title": chunk.title,
            "section": "",
            "source": source,
            "recorded_by": recorded_by_for_memory(root, chunk.source),
            "text": read_text_if_exists(chunk.source),
        }
        index.setdefault(source, full_entry)
        index[chunk.id] = {
            **full_entry,
            "section": chunk.section,
            "recorded_by": recorded_by_for_memory(
                root,
                chunk.source,
                section=chunk.section,
            ),
            "text": chunk.text,
        }
    return index


def _project_summary(root: Path) -> str:
    text = read_text_if_exists(root / "docs" / "wiki" / "project_brief.md")
    for heading in ("What This Project Is", "Project Overview", "Overview", "Purpose"):
        section = _section(text, heading)
        if section:
            return _compact(section, 620)
    pyproject = read_text_if_exists(root / "pyproject.toml")
    match = re.search(r'^description\s*=\s*["\'](.+?)["\']\s*$', pyproject, re.MULTILINE)
    if match:
        return _compact(match.group(1), 620)
    return f"Reviewed project memory for {root.name}."


def _agent_rules(root: Path) -> list[str]:
    text = read_text_if_exists(root / "AGENTS.md")
    rules: list[str] = []
    for line in text.splitlines():
        clean = re.sub(r"^\s*[-*]\s+", "", line).strip()
        if clean == line.strip() or not clean:
            continue
        if "vibewiki_" in clean or "vibewiki context" in clean:
            continue
        value = _compact(clean, 180)
        if value and value not in rules:
            rules.append(value)
        if len(rules) == 10:
            break
    return rules


def _section(text: str, heading: str) -> str:
    if not text:
        return ""
    pattern = re.compile(
        rf"^##+\s+{re.escape(heading)}\s*$\n(.*?)(?=^##+\s+|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _kind(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return clean or "memory"


def _compact(value: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", value).strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)].rstrip() + "..."


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(int(value), high))


def _require_workspace(root: Path) -> None:
    if not (root / ".vibewiki").is_dir():
        raise ValueError(f"Not a VibeWiki project: {root}. Run `vibewiki init` first.")
