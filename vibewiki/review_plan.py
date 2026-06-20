from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .project import ensure_workspace
from .review import latest_patch_dir
from .text_utils import read_text_if_exists, utcish_timestamp


REVIEW_PLAN_FILE = "review_plan.json"
DEFAULT_REVIEW_LIMIT = 8


@dataclass(frozen=True)
class ReviewPlanEntry:
    item: str
    title: str
    kind: str
    recommendation: str
    group: str
    risk: str
    reason: str
    score: int
    duplicate_of: str = ""


@dataclass(frozen=True)
class ReviewPlan:
    path: Path
    payload: dict[str, object]
    items: dict[str, ReviewPlanEntry]


@dataclass(frozen=True)
class CandidateItem:
    item: str
    path: Path
    title: str
    kind: str
    status: str
    body: str


def build_review_plan(
    project: Path,
    *,
    patch_dir: Path | None = None,
    force: bool = False,
    review_limit: int = DEFAULT_REVIEW_LIMIT,
) -> ReviewPlan:
    root = project.resolve()
    ensure_workspace(root)
    selected_patch_dir = (patch_dir or latest_patch_dir(root)).resolve()
    candidates = collect_candidate_items(selected_patch_dir)
    fingerprint = _fingerprint(candidates)
    path = selected_patch_dir / REVIEW_PLAN_FILE

    if not force and path.exists():
        existing = _read_plan_file(path)
        if existing.get("fingerprint") == fingerprint:
            return _payload_to_plan(path, existing)

    payload = _build_payload(selected_patch_dir, candidates, fingerprint, review_limit=review_limit)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _payload_to_plan(path, payload)


def read_review_plan(patch_dir: Path) -> ReviewPlan:
    path = patch_dir / REVIEW_PLAN_FILE
    if not path.exists():
        raise FileNotFoundError(f"No review plan found: {path}")
    return _payload_to_plan(path, _read_plan_file(path))


def collect_candidate_items(patch_dir: Path) -> list[CandidateItem]:
    items: list[CandidateItem] = []
    for folder, fallback_kind in [
        ("findings", "finding"),
        ("skilllets", "skilllet"),
        ("prompt_patterns", "prompt pattern"),
        ("workflows", "workflow"),
    ]:
        directory = patch_dir / folder
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name == "index.md":
                continue
            body = read_text_if_exists(path)
            item_id = path.resolve().relative_to(patch_dir.resolve()).as_posix()
            items.append(
                CandidateItem(
                    item=item_id,
                    path=path,
                    title=_first_heading(body) or path.stem.replace("-", " ").title(),
                    kind=_field(body, "Kind") or _field(body, "Type") or fallback_kind,
                    status=_field(body, "Status") or "candidate",
                    body=body,
                )
            )
    return items


def format_review_plan_summary(plan: ReviewPlan) -> str:
    summary = plan.payload.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    lines = [
        f"Review plan: {plan.path}",
        f"- raw items: {summary.get('raw_items', 0)}",
        f"- review now: {summary.get('review_now', 0)}",
        f"- lower priority: {summary.get('suggested_later', 0)}",
        f"- suggested discard: {summary.get('suggested_discard', 0)}",
    ]
    return "\n".join(lines)


def _build_payload(
    patch_dir: Path,
    candidates: list[CandidateItem],
    fingerprint: str,
    *,
    review_limit: int,
) -> dict[str, object]:
    duplicate_by_key: dict[str, str] = {}
    raw_entries: list[ReviewPlanEntry] = []
    for candidate in candidates:
        duplicate_key = _duplicate_key(candidate)
        duplicate_of = duplicate_by_key.get(duplicate_key, "")
        if not duplicate_of:
            duplicate_by_key[duplicate_key] = candidate.item
        raw_entries.append(_classify_candidate(candidate, duplicate_of=duplicate_of))

    visible_entries = [entry for entry in raw_entries if entry.group != "suggested_discard"]
    visible_entries = sorted(visible_entries, key=lambda entry: (-entry.score, entry.item))
    review_now = {entry.item for entry in visible_entries[: max(1, review_limit)]}

    entries: list[ReviewPlanEntry] = []
    for entry in raw_entries:
        if entry.group == "suggested_discard":
            entries.append(entry)
            continue
        if entry.item in review_now:
            entries.append(
                ReviewPlanEntry(
                    item=entry.item,
                    title=entry.title,
                    kind=entry.kind,
                    recommendation="review_now",
                    group="review_now",
                    risk=entry.risk,
                    reason=entry.reason,
                    score=entry.score,
                    duplicate_of=entry.duplicate_of,
                )
            )
            continue
        entries.append(
            ReviewPlanEntry(
                item=entry.item,
                title=entry.title,
                kind=entry.kind,
                recommendation="suggested_later",
                group="suggested_later",
                risk="low" if entry.risk == "medium" else entry.risk,
                reason=(
                    "Lower priority after the first review batch; preserved as a raw candidate "
                    "and hidden by default to reduce review load."
                ),
                score=entry.score,
                duplicate_of=entry.duplicate_of,
            )
        )

    summary = {
        "raw_items": len(entries),
        "review_now": sum(1 for entry in entries if entry.group == "review_now"),
        "suggested_later": sum(1 for entry in entries if entry.group == "suggested_later"),
        "suggested_discard": sum(1 for entry in entries if entry.group == "suggested_discard"),
    }
    return {
        "version": 1,
        "generated_at": utcish_timestamp(),
        "patch_dir": str(patch_dir),
        "session_id": patch_dir.name,
        "source": "local_rules",
        "review_limit": review_limit,
        "fingerprint": fingerprint,
        "summary": summary,
        "items": {
            entry.item: {
                "title": entry.title,
                "kind": entry.kind,
                "recommendation": entry.recommendation,
                "group": entry.group,
                "risk": entry.risk,
                "reason": entry.reason,
                "score": entry.score,
                "duplicate_of": entry.duplicate_of,
            }
            for entry in sorted(entries, key=lambda value: value.item)
        },
    }


def _classify_candidate(candidate: CandidateItem, *, duplicate_of: str = "") -> ReviewPlanEntry:
    title = candidate.title.strip()
    kind = _normalize_kind(candidate.kind)
    body = candidate.body
    body_lower = body.lower()
    title_lower = title.lower()

    if duplicate_of:
        return ReviewPlanEntry(
            item=candidate.item,
            title=title,
            kind=kind,
            recommendation="suggested_discard",
            group="suggested_discard",
            risk="low",
            reason=f"Likely duplicate of `{duplicate_of}` based on title or summary overlap.",
            score=5,
            duplicate_of=duplicate_of,
        )

    if _looks_like_generic_outcome(candidate):
        return ReviewPlanEntry(
            item=candidate.item,
            title=title,
            kind=kind,
            recommendation="suggested_discard",
            group="suggested_discard",
            risk="low",
            reason=(
                "Looks like a broad session outcome rather than durable memory; keep the raw "
                "candidate for audit, but hide it from the main review queue."
            ),
            score=10,
        )

    if _looks_like_usage_todo(title_lower):
        return ReviewPlanEntry(
            item=candidate.item,
            title=title,
            kind=kind,
            recommendation="suggested_later",
            group="suggested_later",
            risk="low",
            reason=(
                "Looks like a usage example or workflow step captured as a todo, not an urgent "
                "project memory item."
            ),
            score=35,
        )

    if kind in {"skilllet", "prompt pattern", "workflow"}:
        return ReviewPlanEntry(
            item=candidate.item,
            title=title,
            kind=kind,
            recommendation="review_now",
            group="review_now",
            risk="high",
            reason="Reusable unit candidates can affect future agents, so keep them in human review.",
            score=95,
        )

    if kind == "todo":
        score = 82 if _looks_actionable(title_lower, body_lower) else 58
        return ReviewPlanEntry(
            item=candidate.item,
            title=title,
            kind=kind,
            recommendation="review_now",
            group="review_now",
            risk="medium",
            reason="Actionable project follow-up; review whether it belongs in the backlog.",
            score=score,
        )

    if kind in {"issue", "direction", "research_note"}:
        return ReviewPlanEntry(
            item=candidate.item,
            title=title,
            kind=kind,
            recommendation="review_now",
            group="review_now",
            risk="medium",
            reason="Decision-shaped memory; human review should decide whether it is durable.",
            score=78,
        )

    if kind == "knowledge":
        if _has_concrete_evidence(body):
            return ReviewPlanEntry(
                item=candidate.item,
                title=title,
                kind=kind,
                recommendation="review_now",
                group="review_now",
                risk="medium",
                reason="Knowledge candidate includes concrete evidence such as code, commands, paths, or metrics.",
                score=72,
            )
        return ReviewPlanEntry(
            item=candidate.item,
            title=title,
            kind=kind,
            recommendation="suggested_later",
            group="suggested_later",
            risk="low",
            reason="Broad knowledge without concrete operational evidence; keep it, but do not make it default review work.",
            score=45,
        )

    if kind == "idea":
        return ReviewPlanEntry(
            item=candidate.item,
            title=title,
            kind=kind,
            recommendation="suggested_later",
            group="suggested_later",
            risk="low",
            reason="Idea candidates are valuable but usually lower urgency than tasks, issues, or reusable units.",
            score=42,
        )

    return ReviewPlanEntry(
        item=candidate.item,
        title=title,
        kind=kind,
        recommendation="suggested_later",
        group="suggested_later",
        risk="low",
        reason="Unrecognized candidate type; preserved for audit and hidden from the default queue.",
        score=30,
    )


def _payload_to_plan(path: Path, payload: dict[str, object]) -> ReviewPlan:
    raw_items = payload.get("items", {})
    items: dict[str, ReviewPlanEntry] = {}
    if isinstance(raw_items, dict):
        for item, raw in raw_items.items():
            if not isinstance(raw, dict):
                continue
            items[str(item)] = ReviewPlanEntry(
                item=str(item),
                title=str(raw.get("title", "")).strip(),
                kind=str(raw.get("kind", "")).strip(),
                recommendation=str(raw.get("recommendation", "suggested_later")).strip(),
                group=str(raw.get("group", "suggested_later")).strip(),
                risk=str(raw.get("risk", "low")).strip(),
                reason=str(raw.get("reason", "")).strip(),
                score=int(raw.get("score", 0) or 0),
                duplicate_of=str(raw.get("duplicate_of", "")).strip(),
            )
    return ReviewPlan(path=path, payload=payload, items=items)


def _read_plan_file(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Review plan must be a JSON object: {path}")
    return payload


def _fingerprint(candidates: list[CandidateItem]) -> str:
    lines: list[str] = []
    for candidate in candidates:
        stat = candidate.path.stat()
        lines.append(f"{candidate.item}\t{stat.st_mtime_ns}\t{stat.st_size}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _duplicate_key(candidate: CandidateItem) -> str:
    summary = _section(candidate.body, "Summary")
    key = summary or candidate.title
    key = re.sub(r"[^a-z0-9]+", " ", key.lower()).strip()
    return " ".join(key.split())[:180] or candidate.item


def _looks_like_generic_outcome(candidate: CandidateItem) -> bool:
    title_lower = candidate.title.lower()
    body_lower = candidate.body.lower()
    generic_titles = {"issue: outcome", "knowledge: key innovation", "knowledge: suggested positioning"}
    if title_lower in generic_titles:
        return True
    if "candidate issue extracted from a product, research, or daily discussion: outcome:" in body_lower:
        return True
    if "outcome" in title_lower and "it is not yet a mature open-source product" in body_lower:
        return True
    return False


def _looks_like_usage_todo(title_lower: str) -> bool:
    usage_starts = (
        "todo: answering ",
        "todo: approving ",
        "todo: approve or reject ",
        "todo: distilling ",
        "todo: downgrade ",
        "todo: generating ",
        "todo: importing ",
        "todo: mark ",
        "todo: merge ",
        "todo: rendering ",
    )
    return title_lower.startswith(usage_starts)


def _looks_actionable(title_lower: str, body_lower: str) -> bool:
    action_terms = (
        "add",
        "improve",
        "reduce",
        "separate",
        "support",
        "make",
        "build",
        "implement",
        "publish",
        "release",
        "review",
    )
    return any(term in title_lower or term in body_lower[:500] for term in action_terms)


def _has_concrete_evidence(body: str) -> bool:
    concrete_patterns = [
        r"`[^`]+`",
        r"\b[a-zA-Z0-9_./-]+\.(py|md|json|yaml|toml|sv|c|h|cpp)\b",
        r"\b(max_abs_diff|rmse|bad_abs_gt|exit code|VENUS|VEMU|MATLAB|CloudRIC)\b",
    ]
    return any(re.search(pattern, body) for pattern in concrete_patterns)


def _normalize_kind(kind: str) -> str:
    value = kind.strip().lower().replace("_", " ")
    if value == "prompt_pattern":
        return "prompt pattern"
    return value


def _section(text: str, name: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(name)}\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _field(text: str, name: str) -> str:
    prefix = f"{name}:"
    for line in text.splitlines()[:12]:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""
