from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .distill import latest_session_dir
from .models import ReviewPaths
from .project import ensure_workspace
from .text_utils import utcish_timestamp


ITEM_DECISIONS = {"approve", "reject", "defer", "downgrade", "merge", "edit"}


@dataclass(frozen=True)
class ItemDecision:
    item: str
    decision: str
    reviewed_at: str
    target: str = ""
    title: str = ""
    summary: str = ""
    tags: str = ""
    note: str = ""


def latest_patch_dir(project: Path) -> Path:
    patches = sorted((project / ".vibewiki" / "patches").glob("*"))
    patches = [item for item in patches if item.is_dir()]
    if not patches:
        raise FileNotFoundError("No VibeWiki patches found. Run `vibewiki distill` first.")
    return patches[-1]


def review_patches(
    project: Path,
    *,
    patch_dir: Path | None = None,
    approve: bool = False,
    notes: str = "",
    reviewer: str = "human",
    method: str = "manual",
) -> ReviewPaths:
    root = project.resolve()
    ensure_workspace(root)
    selected_patch_dir = patch_dir or latest_patch_dir(root)
    session_id = selected_patch_dir.name
    review_dir = root / ".vibewiki" / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    review_file = review_dir / f"{session_id}.yaml"
    decision = "approved" if approve else "needs_review"
    review_file.write_text(
        f"""session_id: {session_id}
reviewed_at: {utcish_timestamp()}
patch_dir: {selected_patch_dir}
decision: {decision}
reviewer: {reviewer or "human"}
method: {method or "manual"}
notes: |
  {notes or "none"}
""",
        encoding="utf-8",
    )
    return ReviewPaths(session_id=session_id, review_file=review_file)


def item_decisions_path(project: Path, session_id: str) -> Path:
    return project / ".vibewiki" / "reviews" / f"{session_id}.items.json"


def normalize_item_id(patch_dir: Path, item: str) -> str:
    item_path = Path(item)
    if item_path.is_absolute():
        resolved = item_path.resolve()
    else:
        resolved = (patch_dir / item_path).resolve()
    patch_root = patch_dir.resolve()
    try:
        relative = resolved.relative_to(patch_root)
    except ValueError as exc:
        raise ValueError(f"Item must be inside patch directory: {item}") from exc
    if not resolved.exists():
        raise FileNotFoundError(f"Review item not found: {resolved}")
    return relative.as_posix()


def read_item_decisions(project: Path, session_id: str) -> dict[str, ItemDecision]:
    path = item_decisions_path(project, session_id)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_items = payload.get("items", {})
    decisions: dict[str, ItemDecision] = {}
    for item, raw in raw_items.items():
        decisions[item] = ItemDecision(
            item=item,
            decision=str(raw.get("decision", "")).strip(),
            reviewed_at=str(raw.get("reviewed_at", "")).strip(),
            target=str(raw.get("target", "")).strip(),
            title=str(raw.get("title", "")).strip(),
            summary=str(raw.get("summary", "")).strip(),
            tags=str(raw.get("tags", "")).strip(),
            note=str(raw.get("note", "")).strip(),
        )
    return decisions


def record_item_decision(
    project: Path,
    *,
    patch_dir: Path | None = None,
    item: str,
    decision: str,
    target: str = "",
    title: str = "",
    summary: str = "",
    tags: str = "",
    note: str = "",
) -> Path:
    root = project.resolve()
    ensure_workspace(root)
    selected_patch_dir = patch_dir or latest_patch_dir(root)
    session_id = selected_patch_dir.name
    normalized_item = normalize_item_id(selected_patch_dir, item)
    clean_decision = decision.strip().lower()
    if clean_decision not in ITEM_DECISIONS:
        allowed = ", ".join(sorted(ITEM_DECISIONS))
        raise ValueError(f"Unknown item decision `{decision}`. Expected one of: {allowed}.")

    review_dir = root / ".vibewiki" / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    path = item_decisions_path(root, session_id)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {
            "session_id": session_id,
            "patch_dir": str(selected_patch_dir),
            "items": {},
        }

    payload["session_id"] = session_id
    payload["patch_dir"] = str(selected_patch_dir)
    payload["updated_at"] = utcish_timestamp()
    payload.setdefault("items", {})[normalized_item] = {
        "decision": clean_decision,
        "reviewed_at": utcish_timestamp(),
        "target": target.strip(),
        "title": title.strip(),
        "summary": summary.strip(),
        "tags": tags.strip(),
        "note": note.strip(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def update_item_body(
    project: Path,
    *,
    patch_dir: Path | None = None,
    item: str,
    body: str,
) -> Path:
    root = project.resolve()
    ensure_workspace(root)
    selected_patch_dir = patch_dir or latest_patch_dir(root)
    normalized_item = normalize_item_id(selected_patch_dir, item)
    path = (selected_patch_dir / normalized_item).resolve()
    path.write_text(body.rstrip() + "\n", encoding="utf-8")
    return path


def patch_summary(project: Path, patch_dir: Path | None = None) -> str:
    root = project.resolve()
    selected_patch_dir = patch_dir or latest_patch_dir(root)
    files = [
        selected_patch_dir / "knowledge_patch.md",
        selected_patch_dir / "skill_patch.md",
        selected_patch_dir / "agent_rule_patch.md",
        selected_patch_dir / "questions.md",
        selected_patch_dir / "findings",
        selected_patch_dir / "merge_suggestions.md",
        selected_patch_dir / "composable_units.md",
        selected_patch_dir / "skilllets",
        selected_patch_dir / "prompt_patterns",
        selected_patch_dir / "workflows",
    ]
    lines = [f"Patch directory: {selected_patch_dir}"]
    for path in files:
        status = "present" if path.exists() else "missing"
        lines.append(f"- {path.name}: {status}")
    decisions = read_item_decisions(root, selected_patch_dir.name)
    if decisions:
        lines.append(f"- item decisions: {len(decisions)} recorded")
    return "\n".join(lines)


def latest_session_id(project: Path) -> str:
    return latest_session_dir(project).name
