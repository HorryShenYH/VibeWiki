from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .project import ensure_workspace
from .text_utils import read_text_if_exists, utcish_timestamp


ASSURANCE_FILE = "assurance.json"
PROOF_REPORT_FILE = "proof_report.json"


@dataclass(frozen=True)
class AssurancePolicy:
    mode: str = "exceptions"
    auto_promote_clear_knowledge: bool = True
    max_candidates_without_attention: int = 12


@dataclass(frozen=True)
class AssuranceIssue:
    code: str
    category: str
    severity: str
    title: str
    message: str
    items: tuple[str, ...]
    requires_human: bool = True


@dataclass(frozen=True)
class AssuranceReport:
    path: Path
    session_id: str
    status: str
    fingerprint: str
    candidate_count: int
    source_digest: str
    candidate_digest: str
    coverage: dict[str, str]
    issues: tuple[AssuranceIssue, ...]

    @property
    def needs_attention(self) -> bool:
        return any(issue.requires_human for issue in self.issues)

    @property
    def attention_count(self) -> int:
        return sum(1 for issue in self.issues if issue.requires_human)


@dataclass(frozen=True)
class _Candidate:
    item: str
    path: Path
    title: str
    kind: str
    body: str


def load_assurance_policy(project: Path) -> AssurancePolicy:
    values = _read_flat_config(project / ".vibewiki" / "config.yaml")
    configured_mode = values.get("review.mode", "").strip().lower()
    legacy_human_review = _boolean(values.get("review.require_human_approval", "false"))
    return AssurancePolicy(
        mode=configured_mode or ("manual" if legacy_human_review else "exceptions"),
        auto_promote_clear_knowledge=_boolean(
            values.get("review.auto_promote_clear_knowledge", "true")
        ),
        max_candidates_without_attention=_positive_integer(
            values.get("review.max_candidates_without_attention", "12"),
            fallback=12,
        ),
    )


def build_assurance_report(
    project: Path,
    *,
    patch_dir: Path,
    force: bool = False,
) -> AssuranceReport:
    root = project.resolve()
    ensure_workspace(root)
    selected = patch_dir.resolve()
    session_id = selected.name
    path = selected / ASSURANCE_FILE
    candidates = _collect_candidates(selected)
    source_files = _source_files(root, session_id)
    fingerprint = _fingerprint(source_files, selected)

    if not force and path.exists():
        payload = _read_json(path)
        if payload.get("fingerprint") == fingerprint:
            return _report_from_payload(path, payload)

    policy = load_assurance_policy(root)
    issues: list[AssuranceIssue] = []
    source_digest = _digest_files(
        source_files,
        base=root / ".vibewiki" / "sessions" / session_id,
    )
    candidate_digest = _digest_patch(selected)
    source_linkage = "complete"

    session_file = root / ".vibewiki" / "sessions" / session_id / "session.md"
    if not session_file.exists():
        source_linkage = "partial"
        issues.append(
            AssuranceIssue(
                code="source-missing",
                category="provenance",
                severity="high",
                title="Source conversation is missing",
                message="The memory draft cannot be traced back to its captured conversation.",
                items=(str(_relative(session_file, root)),),
            )
        )

    broken_links = tuple(
        candidate.item
        for candidate in candidates
        if _field(candidate.body, "Session") != session_id
    )
    if broken_links:
        source_linkage = "partial"
        issues.append(
            AssuranceIssue(
                code="source-link-mismatch",
                category="provenance",
                severity="high",
                title="Candidate source links do not match",
                message="One or more candidates name a different source session.",
                items=broken_links,
            )
        )

    reusable = tuple(
        candidate.item
        for candidate in candidates
        if _normalize_kind(candidate.kind) in {"skilllet", "prompt-pattern", "workflow"}
    )
    if reusable:
        issues.append(
            AssuranceIssue(
                code="reusable-guidance",
                category="skill",
                severity="high",
                title=(
                    f"{len(reusable)} reusable procedure{'s' if len(reusable) != 1 else ''} "
                    f"{'need' if len(reusable) != 1 else 'needs'} review"
                ),
                message="Reusable guidance can steer future agents, so a person should verify it before trust.",
                items=reusable,
            )
        )

    conflicts = _meaningful_bullets(
        read_text_if_exists(selected / "merge_suggestions.md"),
        "Suggestions",
    )
    existing_unit_conflicts = _existing_unit_conflicts(root, candidates)
    explicit_conflicts = [
        candidate.item
        for candidate in candidates
        if _has_conflict_cue(f"{candidate.title}\n{candidate.body}")
    ]
    conflict_items = tuple(
        dict.fromkeys([*conflicts, *existing_unit_conflicts, *explicit_conflicts])
    )
    if conflict_items:
        issues.append(
            AssuranceIssue(
                code="memory-conflict",
                category="conflict",
                severity="high",
                title="Existing memory may need to be updated",
                message="Keep the disagreement visible and decide whether to merge, replace, or preserve both versions.",
                items=conflict_items,
            )
        )

    questions = _meaningful_bullets(
        read_text_if_exists(selected / "questions.md"),
        "Questions",
    )
    blocking_questions = tuple(
        question for question in questions if reusable or _question_blocks_trust(question)
    )
    if blocking_questions:
        issues.append(
            AssuranceIssue(
                code="incomplete-evidence",
                category="coverage",
                severity="medium",
                title="Important evidence is still incomplete",
                message="The run is marked partial instead of implying that every important claim was checked.",
                items=blocking_questions,
            )
        )

    if len(candidates) > policy.max_candidates_without_attention:
        issues.append(
            AssuranceIssue(
                code="candidate-volume",
                category="quality",
                severity="medium",
                title="The conversation produced too many memory candidates",
                message=(
                    f"{len(candidates)} candidates exceed the local limit of "
                    f"{policy.max_candidates_without_attention}; review the pack as one over-distillation issue."
                ),
                items=tuple(candidate.item for candidate in candidates[:5]),
            )
        )

    duplicate_items = _duplicate_candidates(candidates)
    if duplicate_items:
        issues.append(
            AssuranceIssue(
                code="duplicate-candidates",
                category="deduplication",
                severity="info",
                title="Likely duplicate candidates were collapsed",
                message="Duplicate candidates stay in the raw patch for audit but are excluded from automatic merge.",
                items=duplicate_items,
                requires_human=False,
            )
        )

    human_issues = [issue for issue in issues if issue.requires_human]
    partial = source_linkage == "partial" or bool(blocking_questions)
    status = "partial" if partial else "attention" if human_issues else "clear"
    coverage = {
        "source_linkage": source_linkage,
        "structure": "complete",
        "semantic_consistency": "not_run",
        "reusable_guidance": "human_required" if reusable else "not_applicable",
    }
    payload = {
        "version": 1,
        "generated_at": utcish_timestamp(),
        "generator": "vibewiki.local-assurance-v1",
        "session_id": session_id,
        "status": status,
        "fingerprint": fingerprint,
        "candidate_count": len(candidates),
        "source_digest": source_digest,
        "candidate_digest": candidate_digest,
        "coverage": coverage,
        "summary": {
            "issues": len(issues),
            "needs_attention": len(human_issues),
            "auto_safe": not human_issues,
        },
        "issues": [_issue_payload(issue) for issue in issues],
        "note": (
            "Local assurance verifies provenance, structure, duplication, conflicts, and review gates. "
            "It is integrity evidence, not a guarantee that every claim is correct."
        ),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _report_from_payload(path, payload)


def read_assurance_report(path: Path) -> AssuranceReport:
    return _report_from_payload(path, _read_json(path))


def format_assurance_summary(report: AssuranceReport) -> str:
    lines = [
        f"Memory assurance: {report.status}",
        f"- candidates checked: {report.candidate_count}",
        f"- needs attention: {report.attention_count}",
        f"- semantic consistency: {report.coverage.get('semantic_consistency', 'not_run')}",
    ]
    for issue in report.issues:
        if issue.requires_human:
            lines.append(f"- {issue.severity}: {issue.title}")
    return "\n".join(lines)


def write_proof_report(
    project: Path,
    *,
    patch_dir: Path,
    changed_files: list[Path],
    merge_mode: str,
) -> Path:
    root = project.resolve()
    report = build_assurance_report(root, patch_dir=patch_dir)
    review_text = read_text_if_exists(
        root / ".vibewiki" / "reviews" / f"{patch_dir.name}.yaml"
    )
    outputs = []
    for output in dict.fromkeys(path.resolve() for path in changed_files):
        outputs.append(
            {
                "path": str(_relative(output, root)),
                "sha256": _digest_file(output),
            }
        )
    payload = {
        "version": 1,
        "generated_at": utcish_timestamp(),
        "session_id": patch_dir.name,
        "merge_mode": merge_mode,
        "assurance": {
            "status": report.status,
            "coverage": report.coverage,
            "source_digest": report.source_digest,
            "candidate_digest": report.candidate_digest,
        },
        "decision": {
            "approved": "decision: approved" in review_text,
            "reviewer": _yaml_field(review_text, "reviewer") or "unknown",
            "method": _yaml_field(review_text, "method") or "legacy",
        },
        "outputs": outputs,
        "note": "This report proves which source and candidate snapshot was merged; it does not guarantee correctness.",
    }
    path = patch_dir / PROOF_REPORT_FILE
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _collect_candidates(patch_dir: Path) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for folder, fallback_kind in (
        ("findings", "finding"),
        ("skilllets", "skilllet"),
        ("prompt_patterns", "prompt-pattern"),
        ("workflows", "workflow"),
    ):
        directory = patch_dir / folder
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name == "index.md":
                continue
            body = read_text_if_exists(path)
            candidates.append(
                _Candidate(
                    item=path.resolve().relative_to(patch_dir.resolve()).as_posix(),
                    path=path,
                    title=_first_heading(body) or path.stem,
                    kind=_field(body, "Kind") or _field(body, "Type") or fallback_kind,
                    body=body,
                )
            )
    return candidates


def _existing_unit_conflicts(root: Path, candidates: list[_Candidate]) -> list[str]:
    folders = {
        "skilllet": "skilllets",
        "prompt-pattern": "prompt_patterns",
        "workflow": "workflows",
    }
    conflicts: list[str] = []
    for candidate in candidates:
        folder = folders.get(_normalize_kind(candidate.kind))
        if not folder:
            continue
        target = root / "skills" / folder / candidate.path.name
        if target.exists() and _normalized_body(read_text_if_exists(target)) != _normalized_body(candidate.body):
            conflicts.append(candidate.item)
    return conflicts


def _duplicate_candidates(candidates: list[_Candidate]) -> tuple[str, ...]:
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for candidate in candidates:
        summary = _section(candidate.body, "Summary")
        key = _normalized_body(f"{candidate.kind}\n{candidate.title}\n{summary}")
        if not key:
            continue
        if key in seen:
            duplicates.append(candidate.item)
        else:
            seen[key] = candidate.item
    return tuple(duplicates)


def _question_blocks_trust(question: str) -> bool:
    lowered = question.lower()
    cues = (
        "finally solved",
        "user-facing goal",
        "benchmark note may be incomplete",
        "why are these values correct",
        "remains unsolved",
    )
    return any(cue in lowered for cue in cues)


def _has_conflict_cue(value: str) -> bool:
    lowered = f" {value.lower()} "
    cues = (
        " conflict",
        "conflict ",
        "contradict",
        "inconsistent with",
        "disagrees with",
        "冲突",
        "矛盾",
        "与已有",
    )
    return any(cue in lowered for cue in cues)


def _meaningful_bullets(markdown: str, section_name: str) -> tuple[str, ...]:
    section = _section(markdown, section_name)
    values: list[str] = []
    for line in section.splitlines():
        clean = line.strip()
        if not clean.startswith("- "):
            continue
        value = clean[2:].strip()
        if value and value.lower() not in {"not provided.", "not provided", "none"}:
            values.append(value)
    return tuple(values)


def _section(markdown: str, name: str) -> str:
    lines = markdown.splitlines()
    header = f"## {name}"
    start = -1
    for index, line in enumerate(lines):
        if line.strip() == header:
            start = index + 1
            break
    if start < 0:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def _field(markdown: str, name: str) -> str:
    prefix = f"{name.lower()}:"
    for line in markdown.splitlines():
        if line.lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def _yaml_field(text: str, name: str) -> str:
    return _field(text, name)


def _first_heading(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _normalize_kind(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def _normalized_body(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _source_files(root: Path, session_id: str) -> list[Path]:
    directory = root / ".vibewiki" / "sessions" / session_id
    return [directory / "session.md", directory / "raw_session.md"]


def _fingerprint(source_files: list[Path], patch_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in [*source_files, *_patch_markdown_files(patch_dir)]:
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(read_text_if_exists(path).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _digest_patch(patch_dir: Path) -> str:
    return _digest_files(_patch_markdown_files(patch_dir), base=patch_dir)


def _patch_markdown_files(patch_dir: Path) -> list[Path]:
    return sorted(path for path in patch_dir.rglob("*.md") if path.is_file())


def _digest_files(paths: list[Path], *, base: Path | None = None) -> str:
    digest = hashlib.sha256()
    found = False
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        found = True
        try:
            label = path.resolve().relative_to(base.resolve()) if base else path.name
        except ValueError:
            label = path.name
        digest.update(str(label).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest() if found else ""


def _digest_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _issue_payload(issue: AssuranceIssue) -> dict[str, object]:
    return {
        "code": issue.code,
        "category": issue.category,
        "severity": issue.severity,
        "title": issue.title,
        "message": issue.message,
        "items": list(issue.items),
        "requires_human": issue.requires_human,
    }


def _report_from_payload(path: Path, payload: dict[str, object]) -> AssuranceReport:
    raw_issues = payload.get("issues", [])
    issues: list[AssuranceIssue] = []
    if isinstance(raw_issues, list):
        for raw in raw_issues:
            if not isinstance(raw, dict):
                continue
            raw_items = raw.get("items", [])
            items = tuple(str(item) for item in raw_items) if isinstance(raw_items, list) else ()
            issues.append(
                AssuranceIssue(
                    code=str(raw.get("code", "")),
                    category=str(raw.get("category", "")),
                    severity=str(raw.get("severity", "info")),
                    title=str(raw.get("title", "")),
                    message=str(raw.get("message", "")),
                    items=items,
                    requires_human=bool(raw.get("requires_human", True)),
                )
            )
    raw_coverage = payload.get("coverage", {})
    coverage = (
        {str(key): str(value) for key, value in raw_coverage.items()}
        if isinstance(raw_coverage, dict)
        else {}
    )
    return AssuranceReport(
        path=path,
        session_id=str(payload.get("session_id", path.parent.name)),
        status=str(payload.get("status", "partial")),
        fingerprint=str(payload.get("fingerprint", "")),
        candidate_count=int(payload.get("candidate_count", 0) or 0),
        source_digest=str(payload.get("source_digest", "")),
        candidate_digest=str(payload.get("candidate_digest", "")),
        coverage=coverage,
        issues=tuple(issues),
    )


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_flat_config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    stack: list[tuple[int, str]] = []
    for raw_line in read_text_if_exists(path).splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if ":" not in stripped or stripped.startswith("- "):
            continue
        key, value = stripped.split(":", 1)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        clean_value = value.strip().strip("'\"")
        if not clean_value:
            stack.append((indent, key.strip()))
            continue
        prefix = ".".join(item for _, item in stack)
        full_key = f"{prefix}.{key.strip()}" if prefix else key.strip()
        values[full_key] = clean_value
    return values


def _boolean(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _positive_integer(value: str, *, fallback: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return fallback
    return parsed if parsed > 0 else fallback


def _relative(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return path
